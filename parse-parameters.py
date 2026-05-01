"""
Parser for ``parameters.m`` — generates a combined day-well CSV.

Walks every ``parameters.m`` under ``OUTPUT_DIR`` (one per archive,
produced by ``extract-from-fortress.py``) and writes a single
spreadsheet with one row per (archive, well) to ``PARAMETERS_CSV``.
Run with no arguments:

    python3 parse_parameters.py

Pulls values out with small regex helpers:
* func `extract_string`  — single-quoted scalar, e.g. ``p.EXP_NAME = 'name'``
* func `extract_number`  — bare numeric scalar, e.g. ``p.DT = 40``
* func `extract_array`   — bracketed numeric array, e.g. ``p.LOOP_PER_PHASE = [6, 15]``
* func `extract_cell`    — MATLAB cell array of strings, e.g. ``p.EXP_DRUG = { 'ZEN' ... }``
"""

import re
from dataclasses import dataclass
from typing import Optional

from utils import (TARGET_FILE, OUTPUT_DIR,
                   atomic_write_csv,
                   PARAMETERS_CSV as OUTPUT_FILE)


# ---------------------------------------------------------------------------
# Column specification
# ---------------------------------------------------------------------------
# Column class specifies where/how the given column's value is generated.
# Columns come in different "kinds", which can be:
#     "string"    - p.FIELD = 'str'
#     "number"    - p.FIELD = 123
#     "array"     - p.FIELD = [a, b, ...]; and ``index`` selects one element
#     "cell"      - p.FIELD = { '...' '...' }; one value per well
#     "const"     - literal constant, same on every row
#     "generated" - computed in build_rows (e.g. well_number and date_measured)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Column:
  name: str                    # Name of the output column
  kind: str                    # Type of the output column (should be an enum???)
  source: str = ""             # MATLAB field name, or constant value
  index: Optional[int] = None  # used for the "array" kind


COLUMNS = [
  # ||||| NAME            | KIND       | SOURCE          | INDEX
  Column("archive_id",      "string",    "EXP_NAME"),
  Column("well_number",     "generated"),
  Column("date_measured",   "generated"),
  # Tissue
  Column("cell_line",       "string",    "EXP_CELL"),
  Column("growth_type",     "const",     "pdx"),
  # Treatment
  Column("treatment",       "cell",      "EXP_DRUG"),
  Column("concentration",   "cell",      "EXP_CONC"),
  # Params
  Column("t0",              "array",     "LOOP_PER_PHASE", index=0),
  Column("tf",              "array",     "LOOP_PER_PHASE", index=1),
  Column("dt",              "number",    "DT"),
  Column("f1",              "const",     "0.012"),
  Column("f2",              "const",     "12.5"),
  # Meta
  Column("operator_name",   "string",    "EXP_OPERATOR"),
  Column("system",          "string",    "EXP_SYSTEM"),
  Column("plate_note",      "string",    "NOTE"),
  Column("fortress_status", "const",     "verified"),
]


# ---------------------------------------------------------------------------
# Extractors — one per MATLAB value type we care about
#
# Extractors use regular expressions (aka regex) to find relevant vars.
# An example of a regex is [^_]* and it can "match" different types of text;
# [^_]* will match the word potato but not the word po_tato.
# Here [^_] means any symbol but _
# And the * means "repeat the previous regex [^_] any number of times"
# Therefore the [^_]* regex will find any arrangements of symbols without _.
#
# A more complex regex like p\.{field}\s*=\s*'([^']*)'
# Will match with anything of the form
# p.{field} = 'text with more text'
# which can help us find relevant variables
#
# Helpful tools for understanding regexes visually are
# regexper.com and dcode.fr/regular-expression-analyser
# ---------------------------------------------------------------------------

def extract_string(text, field):
  """Return the value of p.{field} = 'str'. Asserts the field exists."""
  m = re.search(rf"p\.{field}\s*=\s*'([^']*)'", text)
  assert m, f"could not find p.{field} = '...'"
  return m.group(1)


def extract_number(text, field):
  """Return the value of p.{field} = <number> as a string. Asserts the field exists."""
  m = re.search(rf"p\.{field}\s*=\s*([-+\d.eE]+)", text)
  assert m, f"could not find p.{field} = <number>"
  return m.group(1)


def extract_array(text, field):
  """Return the elements of p.{field} = [a, b, ...] as strings. Asserts the field exists."""
  m = re.search(rf"p\.{field}\s*=\s*\[([^\]]*)\]", text)
  assert m, f"could not find p.{field} = [...]"
  return re.findall(r"-?\d+(?:\.\d+)?", m.group(1))


def extract_cell(text, field):
  """Return the strings inside p.{field} = { '...' '...' }. Asserts the field exists."""
  m = re.search(rf"p\.{field}\s*=\s*\{{(.*?)\}}", text, re.DOTALL)
  assert m, f"could not find p.{field} = {{...}}"
  return re.findall(r"'([^']*)'", m.group(1))


# ---------------------------------------------------------------------------
# Generated values
# ---------------------------------------------------------------------------

def date_from_archive_id(archive_id):
  """Turn 20250827SM into 2025-08-27. Error if no leading date."""
  m = re.match(r"(\d{4})(\d{2})(\d{2})", archive_id)
  assert m, f"archive_id {archive_id!r} does not start with YYYYMMDD"
  return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


# ---------------------------------------------------------------------------
# Row construction
# ---------------------------------------------------------------------------

def build_rows(text, source_path):
  """Parse contents of a parameters.m into a list of CSV rows."""

  # First pass: resolve everything that does not depend on the well index.
  # We are just working with archive-level info right now
  archive_info = {}
  cell_columns = {}

  for col in COLUMNS:
    if col.kind == "string":
      archive_info[col.name] = extract_string(text, col.source)
    elif col.kind == "number":
      archive_info[col.name] = extract_number(text, col.source)
    elif col.kind == "array":
      arr = extract_array(text, col.source)
      archive_info[col.name] = arr[col.index] if col.index is not None and col.index < len(arr) else ""
    elif col.kind == "const":
      archive_info[col.name] = col.source
    elif col.kind == "cell":
      cell_columns[col.name] = extract_cell(text, col.source)
    elif col.kind == "generated":
      pass  # filled in per row below
    else:
      raise ValueError(f"unknown column kind: {col.kind!r} for {col.name}")

  # All "cell" type columns must agree on the well count
  lengths = {name: len(values) for name, values in cell_columns.items()}
  assert len(set(lengths.values())) <= 1, (
    f"{source_path}: per-well arrays disagree in length: {lengths}"
  )
  n_wells = next(iter(lengths.values()), 0)

  # Second pass: emit one row per well.
  # Generated columns are computed inline below — add another line here
  # if you introduce a new Column(..., "generated") entry.
  date_measured = date_from_archive_id(archive_info["archive_id"])

  rows = []
  for well in range(1, n_wells + 1):
    row = dict(archive_info)
    for name, values in cell_columns.items():
      row[name] = values[well - 1]
    row["well_number"] = str(well)
    row["date_measured"] = date_measured
    rows.append(row)
  return rows


# === MAIN ===

assert OUTPUT_DIR.is_dir(), f"The output directory {OUTPUT_DIR} does not exist"

# Each extracted archive lives at OUTPUT_DIR/<archive_id>/<TARGET_FILE>;
# walking that glob is simpler than re-reading the archives CSV.
param_files = sorted(OUTPUT_DIR.glob(f"*/{TARGET_FILE}"))

if not param_files:
  print(f"No {TARGET_FILE} files found under {OUTPUT_DIR}.")
  raise SystemExit(0)

print(f"\n{'='*60}")
print(f"Parsing {len(param_files)} {TARGET_FILE} files")
print(f"{'='*60}\n")

all_rows = []
n_ok = 0
n_skipped = 0

for path in param_files:
  archive_id = path.parent.name
  try:
    text = path.read_text(errors='replace')
    rows = build_rows(text, path)
  except (AssertionError, OSError, ValueError) as e:
    # One bad parameters.m shouldn't kill the whole batch — report and move on.
    print(f"  SKIP {archive_id}: {e}")
    n_skipped += 1
    continue
  all_rows.extend(rows)
  n_ok += 1
  print(f"  OK   {archive_id}: {len(rows)} wells")

# Header order is taken straight from COLUMNS, so reordering the
# spec at the top of this file reorders the output columns.
fieldnames = [c.name for c in COLUMNS]
atomic_write_csv(OUTPUT_FILE, fieldnames, all_rows)

print(f"\nDone: {n_ok} parsed, {n_skipped} skipped, {len(all_rows)} rows total")
print(f"Results written to {OUTPUT_FILE}")

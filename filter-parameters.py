"""
Filter parameters.csv down to only the (archive_id, well_number) pairs
listed in the original filenames.csv (entries like 'archive_id(well_number)').

parse_parameters.py emits one row per well in every archive's parameters.m;
this script narrows that output to just the wells the project asked for
in the first place.
"""

import csv
import re

from utils import (atomic_write_csv, read_csv_as_dicts,
                   FILENAMES_CSV,
                   PARAMETERS_CSV as INPUT_FILE,
                   FILTERED_PARAMETERS_CSV as OUTPUT_FILE)

# Each filenames.csv entry looks like '20241102SM(1)' —
# archive_id, then (well_number) in parens.
KEY_PATTERN = re.compile(r"^\s*(.+?)\((\d+)\)\s*$")


def load_keys(path):
  '''Read filenames.csv and return a set of (archive_id, well_number) pairs.'''
  keys = set()
  # utf-8-sig strips the BOM that Excel often adds.
  with open(path, encoding="utf-8-sig", newline="") as f:
    reader = csv.reader(f)
    for line_num, row in enumerate(reader, start=1):
      if not row or not row[0].strip():
        continue
      m = KEY_PATTERN.match(row[0])
      if not m:
        print(f"  warning: {path.name}:{line_num} unrecognized: {row[0]!r}")
        continue
      keys.add((m.group(1), m.group(2)))
  return keys


# === MAIN ===

assert INPUT_FILE.is_file(),    f"The parameters file {INPUT_FILE} does not exist"
assert FILENAMES_CSV.is_file(), f"The filenames file {FILENAMES_CSV} does not exist"

print(f"\n{'='*60}")
print(f"Filtering {INPUT_FILE.name} against {FILENAMES_CSV.name}")
print(f"{'='*60}\n")

keys = load_keys(FILENAMES_CSV)
print(f"  {len(keys)} (archive_id, well_number) keys loaded from {FILENAMES_CSV.name}")

header, rows = read_csv_as_dicts(INPUT_FILE)

# parse_parameters.py emits these as the first two columns; if they are
# missing the input is the wrong file or hasn't been parsed yet.
for required in ('archive_id', 'well_number'):
  assert required in header, (
    f"'{required}' column not found in {INPUT_FILE} — run parse_parameters.py first"
  )

kept = [row for row in rows
        if (row['archive_id'].strip(), row['well_number'].strip()) in keys]
dropped = len(rows) - len(kept)

atomic_write_csv(OUTPUT_FILE, header, kept)

print(f"\nDone: {len(kept)} kept, {dropped} dropped")
print(f"Results written to {OUTPUT_FILE}")

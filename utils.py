# Shared configuration and helpers for the Fortress scripts.
# EDIT THIS FILE to match your project's Fortress layout.

import pathlib as p
import csv
import os

# === EDIT THIS FOR YOUR PROJECT ===
# Where the input CSV lives and where extracted files go.
WORKING_DIR             = p.Path('/home/your_username/project_name')
FILENAMES_CSV           = WORKING_DIR / 'filenames.csv'             # extract-ids.py input
ARCHIVES_CSV            = WORKING_DIR / 'archives.csv'              # the running spreadsheet
OUTPUT_DIR              = WORKING_DIR / 'extracted'                 # where target files land
LOG_DIR                 = OUTPUT_DIR / 'logs'                       # per-archive htar logs
PARAMETERS_CSV          = WORKING_DIR / 'parameters.csv'            # parse_parameters.py output
FILTERED_PARAMETERS_CSV = WORKING_DIR / 'parameters.filtered.csv'   # filter_parameters.py output
# ==================================

# Archives on Fortress are expected at:
#   {GROUP_PATH}/{year}_Reconstructed/{archive_id}{TAR_SUFFIX}
# e.g. /group/nolte/2024_Reconstructed/20241102SM_A.tar
GROUP_PATH = '/group/nolte'
TAR_SUFFIX = '_A.tar'
#             ^ Sometimes this standard is not upheld within fortress.
#               Check manually


# File to get out of each tar during extraction.
# You will have to tinker if you want to extract a pattern instead
TARGET_FILE = 'parameters.m'


def tar_path_for(archive_id):
  '''
  Returns the Fortress path for the tar corresponding to `archive_id`.
  Assumes the first 4 characters of the id are the year.
  '''
  year = archive_id[:4]
  return f"{GROUP_PATH}/{year}_Reconstructed/{archive_id}{TAR_SUFFIX}"


def atomic_write_csv(path, header, rows):
  '''
  Write `rows` (list of dicts) to `path` atomically.
  Writes to a temp file and renames; any interruption leaves the
  previous file intact rather than truncating in place.
  '''
  path = p.Path(path)
  tmp = path.with_suffix(path.suffix + '.tmp')
  with open(tmp, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    f.flush()                  # push Python's buffer to the OS
    os.fsync(f.fileno())       # push OS's buffer to the disk
  os.replace(tmp, path)        # atomic rename


def _looks_like_archive_id(s):
  '''An archive id starts with a 4-digit year (see `tar_path_for`).'''
  return len(s) >= 4 and s[:4].isdigit()


def read_csv_as_dicts(path, extra_cols=(), fallback_header=None):
  '''
  Read a CSV into (header, rows-as-dicts).
  Detects whether row 0 is a header by checking whether its first cell
  looks like an archive id (starts with a 4-digit year). If it does not
  look like an id, row 0 is treated as a header; otherwise `fallback_header`
  must be provided and is used to name the columns.
  Any `extra_cols` missing from the header are appended.
  Short rows are padded so every row dict has every header key.
  '''
  with open(path, newline='', encoding='utf-8-sig') as f:
    raw_rows = list(csv.reader(f))

  first_cell = raw_rows[0][0].strip() if raw_rows and raw_rows[0] else ''
  has_header = bool(raw_rows) and not _looks_like_archive_id(first_cell)

  if has_header:
    header = list(raw_rows[0])
    data_rows = raw_rows[1:]
  else:
    assert fallback_header is not None, (
      f"{path} appears to have no header row; "
      f"pass fallback_header to name the columns."
    )
    header = list(fallback_header)
    data_rows = raw_rows

  for col in extra_cols:
    if col not in header:
      header.append(col)

  rows = [
    {col: (raw[i] if i < len(raw) else '') for i, col in enumerate(header)}
    for raw in data_rows
  ]
  return header, rows

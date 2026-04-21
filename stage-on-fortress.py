from datetime import datetime
import pathlib as p
import subprocess
import select
import time
import csv
import sys
import os

from fortress_utils import tar_path_for, TARGET_FILE

# === EDIT THIS FOR YOUR PROJECT ===
WORKING_DIR = p.Path('/home/your_username/project_name')
INPUT_FILE  = WORKING_DIR / 'archives.csv'

STAGE_COLS = ['Stage Requested Timestamp']
HEARTBEAT_SECONDS = 10  # how often to refresh the live status line


def save_csv(header, rows): # {{{
  '''Write updated rows back to the input CSV atomically.
  Writes to a temp file and renames; an interruption leaves the
  previous file intact rather than truncating in place.'''
  tmp = INPUT_FILE.with_suffix(INPUT_FILE.suffix + '.tmp')
  with open(tmp, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    f.flush()
    os.fsync(f.fileno())
  os.replace(tmp, INPUT_FILE)
# }}}


# === Main ===

assert (INPUT_FILE.is_file()), f"The input file {INPUT_FILE} does not exist"

with open(INPUT_FILE, newline='', encoding='utf-8-sig') as f:
  raw_rows = list(csv.reader(f))

header = raw_rows[0]
assert 'On Fortress' in header, (
  f"'On Fortress' column not found — run inspect-fortress.py first"
)
assert 'Is Staged' in header, (
  f"'Is Staged' column not found — run inspect-fortress.py first"
)
assert f'{TARGET_FILE} Local' in header, (
  f"'{TARGET_FILE} Local' column not found — run inspect-fortress.py first"
)

for col in STAGE_COLS:
  if col not in header:
    header.append(col)

archive_col = header[0]

rows = []
for raw in raw_rows[1:]:
  row = {col: (raw[i] if i < len(raw) else '') for i, col in enumerate(header)}
  rows.append(row)

# Build the list of tars that need staging
to_stage = []  # (row_index, tar_path)
already_staged = 0
already_extracted = 0

for i, row in enumerate(rows):
  archive = row[archive_col].strip()
  if not archive:
    continue
  # Skip archives that not on Fortress
  if row['On Fortress'] != 'Yes':
    continue
  # Skip archives that are saved locally
  elif row[f'{TARGET_FILE} Local'] == 'Yes':
    already_extracted += 1
    continue
  # Skip archives that are staged
  elif row['Is Staged'] == 'Yes':
    already_staged += 1
    continue

  to_stage.append((i, tar_path_for(archive)))

print(f"{'='*60}")
print(f"Staging summary")
print(f"{'='*60}")
print(f"  Already staged:     {already_staged}")
print(f"  Already extracted:  {already_extracted}")
print(f"  To stage:           {len(to_stage)}")
print()

if not to_stage:
  print("Nothing to stage.")
  raise SystemExit(0)

for _, tar in to_stage:
  print(f"  {tar}")

# Record the request timestamp BEFORE waiting on hsi, and save
# immediately — the CSV reflects submission time even if you Ctrl+C
# while hsi is still running (the request stays queued in HPSS).
timestamp = datetime.now().isoformat(timespec='seconds')
for idx, _ in to_stage:
  rows[idx]['Stage Requested Timestamp'] = timestamp
save_csv(header, rows)

print(f"\nSubmitting bulk stage request for {len(to_stage)} tars...")
print(f"Safe to Ctrl+C — the stage request stays queued in HPSS.\n")

tar_paths = [tar for _, tar in to_stage]
# -A requests asynchronous submission where supported; harmless if ignored
stage_cmd = "stage -A " + " ".join(tar_paths)

proc = subprocess.Popen(
  ["hsi", stage_cmd],
  stdout=subprocess.PIPE,
  stderr=subprocess.STDOUT,
  text=True,
  bufsize=1,
)

start = time.time()
last_output = start
status_line_active = False  # True while a \r-updated line is on screen

def clear_status():
  '''Erase the in-place status line so real output can print cleanly.'''
  global status_line_active
  if status_line_active:
    sys.stdout.write("\r\033[K")  # \r to start of line, \033[K to erase to EOL
    sys.stdout.flush()
    status_line_active = False

# Poll stdout with a short timeout so the status line updates in place
while True:
  ready, _, _ = select.select([proc.stdout], [], [], HEARTBEAT_SECONDS)
  if ready:
    line = proc.stdout.readline()
    if not line:
      break  # EOF
    clear_status()
    elapsed = time.time() - start
    print(f"  [{elapsed:>6.1f}s] {line.rstrip()}", flush=True)
    last_output = time.time()
  else:
    if proc.poll() is not None:
      break
    elapsed = time.time() - start
    silent = time.time() - last_output
    # \r returns the cursor to column 0; the next write overwrites
    # whatever was there, so the line updates in place instead of scrolling
    sys.stdout.write(
      f"\r  [{elapsed:>6.1f}s] waiting on hsi ({silent:.0f}s silent)\033[K"
    )
    sys.stdout.flush()
    status_line_active = True

clear_status()
proc.wait()
total = time.time() - start

if proc.returncode != 0:
  print(f"\nhsi stage returned non-zero exit code: {proc.returncode}")
  raise SystemExit(proc.returncode)

print(f"\n{'='*60}")
print(f"Staging requested for {len(to_stage)} files at {timestamp}")
print(f"hsi submission took {total:.1f}s")
print(f"Re-run inspect-fortress.py to refresh 'Is Staged', then")
print(f"run extract-from-fortress.py when the files show DISK state.")
print(f"{'='*60}")

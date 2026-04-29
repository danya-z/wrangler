from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import pathlib as p
import subprocess

from utils import (tar_path_for, TARGET_FILE,
                   atomic_write_csv, read_csv_as_dicts,
                   ARCHIVES_CSV as INPUT_FILE,
                   OUTPUT_DIR, LOG_DIR)

# Columns that this script writes into the CSV
EXTRACT_COLS = [f'{TARGET_FILE} Local', 'Return Code', 'End-of-Download Timestamp']


def extract(tar): # {{{
  '''
  Extracts the TARGET_FILE from the given tar, e.g.
  /group/nolte/2020_Reconstructed/20201122SM_A.tar -> 20201122SM_A/parameters.m
  '''
  stem = p.Path(tar).stem
  logfile = LOG_DIR / f"htar_{stem}.log"
  inner_path = f"{stem}/{TARGET_FILE}"

  print(f"  Extracting {stem}...")
  with open(logfile, "w") as log:
    proc = subprocess.Popen(
      ["htar", "-xf", tar, inner_path],
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      errors='replace',  # htar sometimes emits non-UTF-8 bytes
      cwd=OUTPUT_DIR,
    )
    for line in proc.stdout:
      log.write(line)
    proc.wait()

  has_target = (OUTPUT_DIR / stem / TARGET_FILE).is_file()
  return stem, proc.returncode, has_target
# }}}

# === MAIN ===

# Make sure the working directories and the input file exist {{{
OUTPUT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)
assert (OUTPUT_DIR.is_dir()),  f"Failed to create the output directory {OUTPUT_DIR}"
assert (LOG_DIR.is_dir()),     f"Failed to create the log directory {LOG_DIR}"
assert (INPUT_FILE.is_file()), f"The input file {INPUT_FILE} does not exist"
# }}}

# Read the CSV — expect it to have been inspected first
header, rows = read_csv_as_dicts(INPUT_FILE, extra_cols=EXTRACT_COLS)
assert 'On Fortress' in header, (
  f"'On Fortress' column not found — run inspect-fortress.py first"
)

archive_col = header[0]

# Build extraction queue: on fortress, not yet extracted
tar_queue = []  # (row_index, tar_path)
for i, row in enumerate(rows):
  archive = row[archive_col].strip()
  if not archive:
    continue
  if row['On Fortress'] != 'Yes':
    continue
  if row.get('Return Code'):
    print(f"  {archive}: already extracted (rc={row['Return Code']}), skipping")
    continue
  if row.get(f'{TARGET_FILE} Local') == 'Yes':
    print(f"  {archive}: {TARGET_FILE} already present locally, skipping")
    continue

  tar_queue.append((i, tar_path_for(archive)))

if not tar_queue:
  print("Nothing to extract.")
  raise SystemExit(0)

print(f"\n{'='*60}")
print(f"Extracting {TARGET_FILE} from {len(tar_queue)} tars")
print(f"{'='*60}\n")

# Map tar stems back to row indices for updating the CSV
stem_to_row = {p.Path(tar).stem: idx for idx, tar in tar_queue}

# Create a pool of 8 worker threads (more reads could block htar)
# They work in parallel and close on completion
with ThreadPoolExecutor(max_workers=8) as pool:
  # pool.submit makes each worker run extract(tar)
  # 'futures' maps each return placeholder (future) to its tar path,
  # so you can look up which tar was completed when a thread's job finishes
  # {
  # <Future> (incomplete, placeholder)    : "/path/to/A.tar",
  # <Future> (complete,   function return): "/path/to/B.tar",
  # ...
  # }
  futures = {pool.submit(extract, tar): tar for _, tar in tar_queue}
  # 'as_completed' returns futures *as jobs complete*
  for fut in as_completed(futures):
    stem, returncode, has_target = fut.result()
    idx = stem_to_row[stem]
    rows[idx][f'{TARGET_FILE} Local'] = 'Yes' if has_target else 'No'
    rows[idx]['Return Code'] = str(returncode)
    rows[idx]['End-of-Download Timestamp'] = datetime.now().isoformat(timespec='seconds')
    print(f"  Done: {stem}  rc={returncode}  {TARGET_FILE}={'Yes' if has_target else 'No'}")
    atomic_write_csv(INPUT_FILE, header, rows)

save_csv(header, rows)
extracted   = sum(1 for r in rows if r.get('Return Code'))
have_target = sum(1 for r in rows if r.get(f'{TARGET_FILE} Local') == 'Yes')
print(f"\nDone: {extracted} extracted, {have_target} have {TARGET_FILE}")
print(f"Results written to {INPUT_FILE}")

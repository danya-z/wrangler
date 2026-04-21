from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import pathlib as p
import subprocess
import csv
import os

WORKING_DIR = p.Path('/home/dzhumati/pdx')
INPUT_FILE = WORKING_DIR / 'pdx-plates.csv'
OUTPUT_DIR = WORKING_DIR / 'pdx-files'
LOG_DIR    = OUTPUT_DIR / 'logs'

# Columns that this script writes into the CSV
EXTRACT_COLS = ['params.m Local', 'Return Code', 'End-of-Download Timestamp']


def extract(tar): # {{{
  '''
  Extracts the parameters.m file given the adress in the following format
  /group/nolte/2020_Reconstructed/20201122SM_A.tar
  '''
  stem = p.Path(tar).stem
  logfile = LOG_DIR / f"htar_{stem}.log"
  inner_path = f"{stem}/parameters.m"

  print(f"  Extracting {stem}...")
  with open(logfile, "w") as log:
    proc = subprocess.Popen(
      ["htar", "-xf", tar, inner_path],
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      cwd=OUTPUT_DIR,
    )
    for line in proc.stdout:
      log.write(line)
    proc.wait()

  has_params = (OUTPUT_DIR / stem / "parameters.m").is_file()
  return stem, proc.returncode, has_params
# }}}

def save_csv(header, rows): # {{{
  '''Write updated rows back to the input CSV atomically.'''
  tmp = INPUT_FILE.with_suffix(INPUT_FILE.suffix + '.tmp')
  with open(tmp, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    f.flush()
    os.fsync(f.fileno())
  os.replace(tmp, INPUT_FILE)
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
with open(INPUT_FILE, newline='', encoding='utf-8-sig') as f:
  raw_rows = list(csv.reader(f))

header = raw_rows[0]
assert 'On Fortress' in header, (
  f"'On Fortress' column not found — run inspect-fortress.py first"
)

# Add extraction columns if missing
for col in EXTRACT_COLS:
  if col not in header:
    header.append(col)

plate_col = header[0]

rows = []
for raw in raw_rows[1:]:
  row = {col: (raw[i] if i < len(raw) else '') for i, col in enumerate(header)}
  rows.append(row)

# Build extraction queue: on fortress, not yet extracted
tar_queue = []  # (row_index, tar_path)
for i, row in enumerate(rows):
  plate = row[plate_col].strip()
  if not plate:
    continue
  if row['On Fortress'] != 'Yes':
    continue
  if row.get('Return Code'):
    print(f"  {plate}: already extracted (rc={row['Return Code']}), skipping")
    continue
  if row.get('params.m Local') == 'Yes':
    print(f"  {plate}: parameters.m already present locally, skipping")
    continue

  year = plate[:4]
  tar_queue.append((i, f"/group/nolte/{year}_Reconstructed/{plate}_A.tar"))

if not tar_queue:
  print("Nothing to extract.")
  raise SystemExit(0)

print(f"\n{'='*60}")
print(f"Extracting parameters.m from {len(tar_queue)} tars")
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
    stem, returncode, has_params = fut.result()
    idx = stem_to_row[stem]
    rows[idx]['params.m Local'] = 'Yes' if has_params else 'No'
    rows[idx]['Return Code'] = str(returncode)
    rows[idx]['End-of-Download Timestamp'] = datetime.now().isoformat(timespec='seconds')
    print(f"  Done: {stem}  rc={returncode}  params={'Yes' if has_params else 'No'}")
    save_csv(header, rows)

save_csv(header, rows)
extracted = sum(1 for r in rows if r.get('Return Code'))
have_params = sum(1 for r in rows if r.get('params.m Local') == 'Yes')
print(f"\nDone: {extracted} extracted, {have_params} have parameters.m")
print(f"Results written to {INPUT_FILE}")

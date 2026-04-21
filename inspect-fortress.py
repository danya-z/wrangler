from datetime import datetime
import pathlib as p
import subprocess
import csv
import os

from fortress_utils import tar_path_for, TARGET_FILE

# === EDIT THIS FOR YOUR PROJECT ===
WORKING_DIR = p.Path('/home/your_username/project_name')
INPUT_FILE  = WORKING_DIR / 'archives.csv'
OUTPUT_DIR  = WORKING_DIR / 'extracted'

STATUS_COLS = ['On Fortress', 'Is Staged', 'Permissions',
               f'{TARGET_FILE} in Tar', f'{TARGET_FILE} Local',
               'Inspection Timestamp']


def ask_about_header(): # {{{
  '''Asks the user if the input CSV has a header line.'''
  print(f"Preview of {INPUT_FILE}:")
  with open(INPUT_FILE, newline='', encoding='utf-8-sig') as f:
    reader = csv.reader(f)
    for i, row in enumerate(reader):
      if i >= 10:
        break
      print(f"  {row}")
  print()

  while True:
    answer = input(f"Does {INPUT_FILE} have a header line? (yes/no): ").strip().lower()
    if answer in ("yes", "y"):
      return True
    if answer in ("no", "n"):
      return False
    print("Please type 'yes' or 'no'.")
# }}}

def read_input(): # {{{
  '''Read the input CSV, adding status columns if needed. Returns (header, rows).'''
  has_header = ask_about_header()

  with open(INPUT_FILE, newline='', encoding='utf-8-sig') as f:
    raw_rows = list(csv.reader(f))

  if has_header:
    header = raw_rows[0]
    data_rows = raw_rows[1:]
  else:
    header = ['Archive']
    data_rows = raw_rows

  # Add missing status columns
  for col in STATUS_COLS:
    if col not in header:
      header.append(col)

  # Convert to list of dicts, padding short rows with empty strings
  rows = []
  for raw in data_rows:
    row = {col: (raw[i] if i < len(raw) else '') for i, col in enumerate(header)}
    rows.append(row)

  return header, rows
# }}}

def save_csv(header, rows): # {{{
  '''Write updated rows back to the input CSV atomically.'''
  tmp = INPUT_FILE.with_suffix(INPUT_FILE.suffix + '.tmp')
  with open(tmp, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    f.flush()                   # push Python's buffer to the OS
    os.fsync(f.fileno())        # push OS's buffer to the disk
  os.replace(tmp, INPUT_FILE)   # atomic rename
# }}}

def parse_ls_u_line(line): # {{{
  '''Parse a file line from hsi ls -U output.
  Example: -rw-rw----  1 lim185 nolte-data 11 487867 TAPE 9738040320 Feb 12 2024 20230726L_A.tar
  Returns (permissions, state, filename) or None if not a file listing line.'''
  tokens = line.split()
  if len(tokens) < 8:
    return None
  # File lines start with a permission string like -rw-rw----
  if len(tokens[0]) != 10 or tokens[0][0] not in '-dlcbps':
    return None

  perms = tokens[0]
  state = ''
  filename = ''

  for token in tokens:
    if token in ('TAPE', 'DISK'):
      state = token
    if token.endswith('.tar'):
      filename = token

  if not filename:
    return None
  return perms, state, filename
# }}}

def inspect_archive(archive): # {{{
  '''Check if an archive's tar exists on Fortress, its staging state, and permissions.
  Returns (on_fortress, is_staged, permissions, tar_paths).'''
  base = tar_path_for(archive)
  base_dir = str(p.Path(base).parent)

  result = subprocess.run(
    ["hsi", "ls", "-U", base],
    capture_output=True, text=True
  )

  tar_files = []
  is_staged = ""
  permissions = ""

  # The useful output is in stderr
  for line in result.stderr.strip().splitlines():
    parsed = parse_ls_u_line(line)
    if parsed:
      perms, state, filename = parsed
      tar_files.append(f"{base_dir}/{filename}")
      permissions = perms
      # DISK = staged on disk cache, TAPE = tape only (needs staging)
      is_staged = "Yes" if state == "DISK" else "No"

  on_fortress = "Yes" if tar_files else "No"
  return on_fortress, is_staged, permissions, tar_files
# }}}

def check_tar_contents(tar_path): # {{{
  '''Check if the tarball on Fortress contains the target file.'''
  result = subprocess.run(
    ["htar", "-tvf", tar_path],
    capture_output=True, text=True
  )
  for line in result.stdout.splitlines():
    if TARGET_FILE in line:
      return True
  return False
# }}}

# == MAIN ==

assert (INPUT_FILE.is_file()), f"The input file {INPUT_FILE} does not exist"

header, rows = read_input()
archive_col = header[0]

print(f"\n{'='*60}")
print(f"Inspecting {len(rows)} archives on Fortress")
print(f"{'='*60}\n")

for i, row in enumerate(rows):
  archive = row[archive_col].strip()
  if not archive:
    continue

  print(f"  [{i+1}/{len(rows)}] {archive}...", end=' ', flush=True)
  on_fortress, is_staged, permissions, tar_files = inspect_archive(archive)

  row['On Fortress'] = on_fortress
  row['Is Staged'] = is_staged
  row['Permissions'] = permissions
  row['Inspection Timestamp'] = datetime.now().isoformat(timespec='seconds')

  if on_fortress == 'Yes':
    # Check if the target file exists inside the tarball on Fortress
    in_tar = check_tar_contents(tar_files[0])
    row[f'{TARGET_FILE} in Tar'] = 'Yes' if in_tar else 'No'

    # Check if the target file was already downloaded locally
    stem = p.Path(tar_files[0]).stem
    local = (OUTPUT_DIR / stem / TARGET_FILE).is_file()
    row[f'{TARGET_FILE} Local'] = 'Yes' if local else 'No'

    print(f"found (staged: {is_staged}, perms: {permissions}, "
          f"in tar: {'Yes' if in_tar else 'No'}, local: {'Yes' if local else 'No'})")
  else:
    print("NOT found")

  # Save after each archive so progress is not lost
  save_csv(header, rows)

found   = sum(1 for r in rows if r['On Fortress'] == 'Yes')
missing = sum(1 for r in rows if r['On Fortress'] == 'No')
in_tar  = sum(1 for r in rows if r.get(f'{TARGET_FILE} in Tar') == 'Yes')
local   = sum(1 for r in rows if r.get(f'{TARGET_FILE} Local') == 'Yes')
print(f"\nDone: {found} found, {missing} missing, "
      f"{in_tar} have {TARGET_FILE} in tar, {local} already downloaded")
print(f"Results written to {INPUT_FILE}")

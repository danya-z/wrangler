from datetime import datetime
import pathlib as p
import subprocess

from utils import (tar_path_for, TARGET_FILE,
                   atomic_write_csv, read_csv_as_dicts,
                   ARCHIVES_CSV as INPUT_FILE,
                   OUTPUT_DIR)

STATUS_COLS = ['On Fortress', 'Is Staged', 'Permissions',
               f'{TARGET_FILE} in Tar', f'{TARGET_FILE} Local',
               'Inspection Timestamp']


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
    capture_output=True, text=True, errors='replace',
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
    capture_output=True, text=True, errors='replace',
  )
  for line in result.stdout.splitlines():
    if TARGET_FILE in line:
      return True
  return False
# }}}

# === MAIN ===

assert (INPUT_FILE.is_file()), f"The input file {INPUT_FILE} does not exist"

header, rows = read_csv_as_dicts(INPUT_FILE, extra_cols=STATUS_COLS,
                                 fallback_header=['Archive'])
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
  atomic_write_csv(INPUT_FILE, header, rows)

found   = sum(1 for r in rows if r['On Fortress'] == 'Yes')
missing = sum(1 for r in rows if r['On Fortress'] == 'No')
in_tar  = sum(1 for r in rows if r.get(f'{TARGET_FILE} in Tar') == 'Yes')
local   = sum(1 for r in rows if r.get(f'{TARGET_FILE} Local') == 'Yes')
print(f"\nDone: {found} found, {missing} missing, "
      f"{in_tar} have {TARGET_FILE} in tar, {local} already downloaded")
print(f"Results written to {INPUT_FILE}")

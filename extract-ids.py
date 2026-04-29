# Given a spreadsheet of file names, produce a spreadsheet of unique archive ids.
#
# Assumes the first column of the input file is of the form
#      
#   20241102SM(1)
#   20241102SM(2)
#   ...
#   20240122L(3)
#           ^ note, there is no '_A' like in the archive format  
#
# The trailing `(N)` is stripped, duplicates removed, and the resulting
# archive ids (e.g. 20241102SM_A) are written to the output CSV.

import csv
import re

from utils import WORKING_DIR, ARCHIVES_CSV

# Project paths live in utils.py — only this script's input file is local,
# since none of the other scripts need it.
INPUT_FILE  = WORKING_DIR / 'filenames.csv'
OUTPUT_FILE = ARCHIVES_CSV

# Regex that strips the per-file suffix 
# so different wells withing plate collapse to one id.
SUFFIX_PATTERN = r'\(.*\)'

assert (WORKING_DIR.is_dir()), f"The working directory {WORKING_DIR} does not exist"
assert (INPUT_FILE.is_file()), f"The input file {INPUT_FILE} does not exist"


# === MAIN ===
# A set data structure gives us free deduplication.
archives = set()
with open(INPUT_FILE, newline='', encoding='utf-8-sig') as f:
  reader = csv.reader(f)
  for row in reader:
    if row:
      archive = re.sub(SUFFIX_PATTERN, '', row[0]).strip()
      archives.add(archive)

with open(OUTPUT_FILE, 'w', newline='') as f:
  writer = csv.writer(f)
  writer.writerows([[a] for a in archives])

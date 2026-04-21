import csv
import re

INPUT_FILE = 'pdx-files.csv'
OUTPUT_FILE = 'pdx-plates.csv'

plates = set()
with open (INPUT_FILE, newline='', encoding='utf-8-sig') as f:
  pdx_reader = csv.reader(f)
  for row in pdx_reader:
    if row:
      plate = row[0]
      plate = re.sub(r'\(.*\)', '', plate).strip()
      plates.add(plate)

with open(OUTPUT_FILE, 'w', newline='') as f:
  pdx_writer = csv.writer(f)
  pdx_writer.writerows([[p] for p in plates])

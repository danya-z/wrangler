# wrangler

A small suite of Python scripts for pulling a target file (e.g.
`parameters.m`) out of tar archives stored on Fortress, our HPSS tape
system. The scripts were originally written for the PDX project; this
copy is generalized so anyone on depot can adapt it to their own
archives.

**Project status:** unmaintained. Git history is here as insurance — if
a copy of the scripts misbehaves, recover by re-copying from depot. If
you want to pick the project up, go ahead.


## Getting a copy

Everything lives on depot. To use the scripts, copy the directory into
your home:

```sh
cp -r --exclude=.git /depot/path/to/wrangler ~/
```

The `--exclude=.git` is important: it leaves the git history behind so
your copy is a plain folder, not a broken checkout. If you know git and
want to track changes / contribute fixes, skip the exclude and work in
a clone instead.

No virtualenv, no install step — just run the scripts with whatever
`python3` is on the system. You do need `hsi` and `htar` on your
`PATH`; those come with the Fortress client tools.


## What each script does

The scripts are meant to be run in order. Each one reads a CSV and
writes additional columns back into it, so you build up a single
spreadsheet that tracks the state of every archive.

### `extract-ids.py`
Input: a CSV of file names like `20241102SM(1)`, `20241102SM(2)`, ...
(one per row, first column).
Output: a CSV of unique archive ids (`20241102SM`, `20240122L`, ...)
with the `(N)` suffix stripped and duplicates removed.

Skip this step if you already have a list of archive ids.

### `inspect-fortress.py`
For each id in the archives CSV, asks Fortress:
- does the tar exist?
- is it staged on disk, or still on tape?
- what are its permissions?
- does it contain the target file?
- has the target file already been downloaded locally?

Writes the answers into new columns (`On Fortress`, `Is Staged`,
`Permissions`, `<target> in Tar`, `<target> Local`, `Inspection
Timestamp`). Safe to re-run; it updates in place.

### `stage-on-fortress.py`
Submits a bulk stage request for every tar that is on Fortress but not
yet staged and not yet extracted. Staging pulls tars from tape to
disk, which can take minutes to hours; the request stays queued in
HPSS even if you Ctrl+C the script. Writes a `Stage Requested
Timestamp` column.

After staging, re-run `inspect-fortress.py` to refresh the `Is Staged`
column.

### `extract-from-fortress.py`
For each tar that is on Fortress and not yet extracted locally, pulls
the target file out and saves it under `OUTPUT_DIR/<archive_id>/`.
Runs up to 8 extractions in parallel. Writes `<target> Local`,
`Return Code`, and `End-of-Download Timestamp` columns. Per-archive
`htar` logs land in `OUTPUT_DIR/logs/`.

### `fortress_utils.py`
Shared config and helpers (`tar_path_for`, `atomic_write_csv`,
`read_csv_as_dicts`). Not run directly — edited to match your
project's Fortress layout.


## Typical workflow

Assuming you already have a list of filenames from a Fortress search
or an export:

1. **Edit the config.** Open `fortress_utils.py` and set `GROUP_PATH`,
   `TAR_SUFFIX`, and `TARGET_FILE` for your archive. Then open each of
   the four scripts and edit the `=== EDIT THIS FOR YOUR PROJECT ===`
   block at the top to point at your working directory and input CSV.

2. **(Optional) Collapse filenames to ids.**
   ```sh
   python3 extract-ids.py
   ```
   Produces `archives.csv`.

3. **Inspect what Fortress has.**
   ```sh
   python3 inspect-fortress.py
   ```
   Fills in the status columns. Review the CSV to see what's on tape,
   what's already staged, and what's missing the target file.

4. **Stage the tars that need it.**
   ```sh
   python3 stage-on-fortress.py
   ```
   Submits the bulk stage request. Staging may take a while — come
   back later.

5. **Re-inspect to see what's ready.**
   ```sh
   python3 inspect-fortress.py
   ```
   `Is Staged` should now read `Yes` for the tars HPSS has pulled from
   tape.

6. **Extract.**
   ```sh
   python3 extract-from-fortress.py
   ```
   Downloads the target file from every staged tar. Re-run to retry
   any that failed.


## Assumptions and caveats

- **Archive id convention.** Ids are assumed to start with a 4-digit
  year (e.g. `20241102SM`). The code uses that to build the tar's
  Fortress path (`{GROUP_PATH}/{year}_Reconstructed/{id}{TAR_SUFFIX}`)
  and to auto-detect whether a CSV has a header row. If your ids
  don't start with a year, edit `tar_path_for` and
  `_looks_like_archive_id` in `fortress_utils.py`.
- **Tar naming.** The template above is not universal on Fortress —
  some archives break the convention. `inspect-fortress.py` will
  report them as missing; check manually with `hsi ls`.
- **One target file per tar.** The scripts pull a single file
  (`TARGET_FILE`) out of each tar. Extracting a pattern or multiple
  files requires editing `extract-from-fortress.py`.
- **CSV is the source of truth.** All progress is written back to the
  input CSV atomically (temp file + rename), so a Ctrl+C won't
  corrupt it. If two scripts are run on the same CSV at once, the
  last writer wins.
- **Required tools on `PATH`:** `hsi`, `htar`, `python3` (3.8+).


## If something breaks

Most likely cause: an older copy of the scripts. Re-copy from depot
(`cp -r --exclude=.git /depot/path/to/wrangler ~/`) and try again
before digging in. The git history on depot is the authoritative
version; local copies are snapshots.

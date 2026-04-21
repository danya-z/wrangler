# Shared configuration and helpers for the Fortress scripts.
# EDIT THIS FILE to match your project's Fortress layout.

# Archives on Fortress are expected at:
#   {GROUP_PATH}/{year}_Reconstructed/{archive_id}{TAR_SUFFIX}
# e.g. /group/nolte/2024_Reconstructed/20241102SM_A.tar
GROUP_PATH = '/group/your_group'
TAR_SUFFIX = '_A.tar'

# File to pull out of each tar during extraction.
TARGET_FILE = 'parameters.m'


def tar_path_for(archive):
  '''Returns the Fortress path for the tar corresponding to `archive`.
  Assumes the first 4 characters of the id are the year.'''
  year = archive[:4]
  return f"{GROUP_PATH}/{year}_Reconstructed/{archive}{TAR_SUFFIX}"

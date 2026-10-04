#!/usr/bin/env bash
# Fail when the hackathon sponsor's name appears in any tracked file, file name or commit (spec section 3, rule 1).
# The name comes from $SPONSOR_NAME (a GitHub repository variable in CI), so no file in the repo holds it.
# Anything copied from the hackathon version of VART carries the name, so this catches copies of its code and data.
set -euo pipefail
name="${SPONSOR_NAME:?SPONSOR_NAME is not set}"
found=0
if git grep -l -I -i -F -e "$name" -- . ; then
  echo "sponsor-check: the name appears in the files above" >&2
  found=1
fi
if git ls-files | grep -i -F -e "$name" ; then
  echo "sponsor-check: the name appears in the file names above" >&2
  found=1
fi
# No grep -q: an early exit would SIGPIPE git log, and pipefail would turn a match into a miss.
if git log --all -p | grep -i -F -e "$name" > /dev/null ; then
  echo "sponsor-check: the name appears in git history" >&2
  found=1
fi
[ "$found" -eq 0 ] && echo "sponsor-check: clean"
exit "$found"

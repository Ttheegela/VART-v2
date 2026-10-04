#!/usr/bin/env bash
# Fail when the hackathon sponsor's name appears in any tracked file, file name or commit (spec section 3, rule 1).
# The name comes from $SPONSOR_NAME (a GitHub repository secret in CI), so no file in the repo holds it.
# Anything copied from the hackathon version of VART carries the name, so this catches copies of its code and data.
set -euo pipefail
name="${SPONSOR_NAME:?SPONSOR_NAME is not set}"
# Padding would quietly weaken the search ("Name " misses "Name."), so refuse it. The message never shows the value.
case "$name" in
  [[:space:]]* | *[[:space:]]) echo "sponsor-check: SPONSOR_NAME has leading or trailing whitespace" >&2; exit 1 ;;
esac
# Fail closed: below, a git that cannot read the repository would look the same as a search that found nothing.
git rev-parse --git-dir > /dev/null
top=$(git rev-parse --show-toplevel)
cd "$top" # scan the whole repository, whatever directory this runs from
found=0
if git grep -l -I -i -F -e "$name" -- . ; then
  echo "sponsor-check: the name appears in the files above" >&2
  found=1
fi
# core.quotePath=false: git otherwise prints non-ASCII paths as octal escapes, which hides a non-ASCII name.
if git -c core.quotePath=false ls-files | grep -i -F -e "$name" ; then
  echo "sponsor-check: the name appears in the file names above" >&2
  found=1
fi
# No grep -q: an early exit would SIGPIPE git log, and pipefail would turn a match into a miss.
if git -c core.quotePath=false log --all -p | grep -i -F -e "$name" > /dev/null ; then
  echo "sponsor-check: the name appears in git history" >&2
  found=1
fi
[ "$found" -eq 0 ] && echo "sponsor-check: clean"
exit "$found"

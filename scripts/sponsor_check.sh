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
# Every git read below must fail the script when git fails. In a pipe or an if, a git error reads as "no match" and
# the check prints "clean", so git writes to a file on a line of its own, where set -e stops it.
# The explicit template is deliberate: a bare mktemp -d ignores $TMPDIR on macOS.
tmp=$(mktemp -d "${TMPDIR:-/tmp}/sponsor-check.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
found=0
# git grep exits 0 when it finds the name, 1 when it does not, and anything else (usually 128) when it fails.
grep_status=0
git grep -l -I -i -F -e "$name" -- . || grep_status=$?
case "$grep_status" in
  0) echo "sponsor-check: the name appears in the files above" >&2; found=1 ;;
  1) ;;
  *) echo "sponsor-check: git grep failed" >&2; exit "$grep_status" ;;
esac
# core.quotePath=false: git otherwise prints non-ASCII paths as octal escapes, which hides a non-ASCII name.
git -c core.quotePath=false ls-files > "$tmp/files"
if grep -i -F -e "$name" "$tmp/files" ; then
  echo "sponsor-check: the name appears in the file names above" >&2
  found=1
fi
git -c core.quotePath=false log --all -p > "$tmp/history"
# The history is read from a file, so there is no pipe for grep to close early. Its output is still discarded: the
# matching lines would show the name.
if grep -i -F -e "$name" "$tmp/history" > /dev/null ; then
  echo "sponsor-check: the name appears in git history" >&2
  found=1
fi
[ "$found" -eq 0 ] && echo "sponsor-check: clean"
exit "$found"

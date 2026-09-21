#!/usr/bin/env bash
# Build the release archive for one exact commit (audit G4 / DEBT-01).
#
# Runs in CI, inside a checkout of the repository. `git archive` emits exactly
# the tracked tree of the requested commit — nothing that is merely lying
# around in the working directory, and nothing that a previous release left
# behind. That property is what makes the production build context provable.
#
# Usage:
#   infra/production/make_release_archive.sh <sha> <out.tar.gz> [repo_dir]
#
# Writes <out.tar.gz> and <out.tar.gz>.sha256. Exits non-zero if the archive
# does not match the commit's tree, or if it carries a secrets file.
#
# Regression tests: infra/production/tests/test_release_build_context.py

set -euo pipefail

SHA="${1:-}"
OUT="${2:-}"
REPO="${3:-$(cd "$(dirname "$0")/../.." && pwd -P)}"

if [ -z "$SHA" ] || [ -z "$OUT" ]; then
  echo "usage: make_release_archive.sh <sha> <out.tar.gz> [repo_dir]" >&2
  exit 2
fi

die() { echo "✗ $1" >&2; exit 1; }

command -v git > /dev/null 2>&1 || die "git is required"
command -v tar > /dev/null 2>&1 || die "tar is required"

RESOLVED="$(git -C "$REPO" rev-parse --verify "${SHA}^{commit}" 2>/dev/null || true)"
[ -n "$RESOLVED" ] || die "'$SHA' is not a commit in $REPO"

# The deploy path keys directories off the full SHA. A caller that passes an
# abbreviation would prepare releases/<short> while the gate looks for the
# full one, so refuse rather than silently rewrite what was asked for.
if [ "$RESOLVED" != "$SHA" ]; then
  die "pass the full 40-character SHA: '$SHA' resolves to $RESOLVED"
fi

mkdir -p "$(dirname "$OUT")"
rm -f "$OUT" "$OUT.sha256"

# -n: no timestamp in the gzip header, so the same commit produces a
# byte-identical archive on every run and the checksum below is meaningful.
git -C "$REPO" archive --format=tar "$SHA" | gzip -n -9 > "$OUT"

# --- verification --------------------------------------------------------
# Same tree, no more and no less. A silent mismatch here would put us back
# where DEBT-01 started: a build context nobody can tie to a commit.
expected="$(mktemp)"; actual="$(mktemp)"
unpacked="$(mktemp -d)"
trap 'rm -rf "$expected" "$actual" "$unpacked"' EXIT

# A submodule is a gitlink, not content: `git archive` leaves an empty
# directory where one should be, and the build would silently miss it.
if git -C "$REPO" ls-tree -r "$SHA" | awk '$1 == "160000" { found = 1 } END { exit !found }'; then
  die "the tree of $SHA contains a submodule; git archive cannot carry its content"
fi

# core.quotePath=false: by default git C-escapes any path holding a non-ASCII
# byte ("docs/manual/\320\240...md"). Two documents in this repository have
# Cyrillic names, so the default made this comparison fail on every real tree.
git -C "$REPO" -c core.quotePath=false ls-tree -r --name-only "$SHA" \
  | LC_ALL=C sort > "$expected"

# Unpacked and listed from the filesystem rather than read off `tar -t`:
# GNU tar prints those same names raw while the bsdtar on macOS C-escapes
# them, so a listing-based comparison passed on one machine and failed on the
# other. Extracting also proves the archive is readable, which listing does not.
tar -xzf "$OUT" -C "$unpacked" || die "the archive just written cannot be extracted"
( cd "$unpacked" && find . \( -type f -o -type l \) -print ) \
  | sed 's|^\./||' | LC_ALL=C sort > "$actual"

if ! diff -u "$expected" "$actual" > /dev/null; then
  echo "✗ archive contents differ from the tree of $SHA:" >&2
  diff -u "$expected" "$actual" >&2 || true
  exit 1
fi

# `git archive` cannot include an untracked file, and .env is untracked by
# policy — but the policy is one .gitignore edit away from changing, and this
# archive is copied onto the production host. Check rather than assume.
if leaked="$(awk -F/ '{ n=$NF; if (n == ".env" || (n ~ /^\.env\./ && n !~ /\.example$/)) print }' "$actual")" \
   && [ -n "$leaked" ]; then
  echo "✗ the release archive carries a secrets file:" >&2
  echo "$leaked" >&2
  exit 1
fi

if command -v sha256sum > /dev/null 2>&1; then
  sha256sum "$OUT" | awk '{print $1}' > "$OUT.sha256"
else
  shasum -a 256 "$OUT" | awk '{print $1}' > "$OUT.sha256"
fi

echo "✓ release archive for $SHA"
echo "  path     : $OUT"
echo "  files    : $(wc -l < "$actual" | tr -d ' ')"
echo "  bytes    : $(wc -c < "$OUT" | tr -d ' ')"
echo "  sha256   : $(cat "$OUT.sha256")"

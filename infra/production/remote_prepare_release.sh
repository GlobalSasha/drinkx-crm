#!/usr/bin/env bash
# Unpack one release into a clean, immutable tree on the server (audit G4 /
# DEBT-01).
#
# This script lives in the repository but is executed on the server through
# stdin:
#
#   ssh host "DEPLOY_ROOT=/opt/drinkx-crm bash -s -- <sha>" \
#       < infra/production/remote_prepare_release.sh
#
# Piping it avoids the chicken-and-egg of "ship the code first, then run the
# script that ships the code", and means the version that runs is always the
# one from the commit being released.
#
# Layout it maintains under DEPLOY_ROOT (default /opt/drinkx-crm):
#
#   incoming/<sha>.tar.gz     transfer staging, removed once unpacked
#   releases/<sha>/           the build context — exactly the tree of <sha>
#   releases/.markers/<sha>   digest of the archive that tree came from
#   current -> releases/<sha> flipped by deploy.sh, only after verification
#   shared/.env               secrets, never inside a release tree
#
# Nothing outside releases/ and incoming/ is written, and nothing is ever
# deleted from DEPLOY_ROOT itself: the Docker volumes (drinkx_pg,
# drinkx_redis, drinkx_logs), the compose project name and .env are untouched.
# This is deliberately NOT `rsync --delete /opt/drinkx-crm`, which could take
# the production secrets and any server-owned state with it.
#
# A failure here leaves the previous release running and `current` pointing
# where it already pointed.
#
# Regression tests: infra/production/tests/test_release_build_context.py

set -euo pipefail

SHA="${1:-}"
DEPLOY_ROOT="${DEPLOY_ROOT:-/opt/drinkx-crm}"
KEEP_RELEASES="${KEEP_RELEASES:-5}"

die() { echo "✗ $1" >&2; echo "RELEASE_PREPARE=failed"; exit 1; }

[ -n "$SHA" ] || die "no commit SHA given"

# The SHA becomes a directory name. Anything but 40 hex characters is either a
# mistake or an attempt at path traversal; neither gets to touch the disk.
case "$SHA" in
  *[!0-9a-f]* | "") die "'$SHA' is not a lowercase 40-character commit SHA" ;;
esac
[ "${#SHA}" -eq 40 ] || die "'$SHA' is not a lowercase 40-character commit SHA"

ARCHIVE="${ARCHIVE:-$DEPLOY_ROOT/incoming/$SHA.tar.gz}"
RELEASES="$DEPLOY_ROOT/releases"
TARGET="$RELEASES/$SHA"

[ -f "$ARCHIVE" ] || die "release archive not found: $ARCHIVE"

# --- integrity ----------------------------------------------------------
# The archive crossed a network. Verify it against the checksum CI computed
# before deciding it is the tree of this commit.
# The digest is computed either way: besides the integrity check it is the
# identity of this archive, recorded beside the published tree so a repeat
# preparation of the same SHA can recognise its own work (see "publish").
if command -v sha256sum > /dev/null 2>&1; then
  ARCHIVE_SHA="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
else
  ARCHIVE_SHA="$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')"
fi
if [ -f "$ARCHIVE.sha256" ]; then
  want="$(tr -d ' \t\r\n' < "$ARCHIVE.sha256")"
  [ "$ARCHIVE_SHA" = "$want" ] || die "archive checksum mismatch: got $ARCHIVE_SHA, expected $want"
  echo "✓ archive checksum verified"
else
  echo "⚠ no checksum beside $ARCHIVE — unpacking without an integrity check"
fi

# --- unpack into a private directory ------------------------------------
# Built beside the final location and renamed at the end, so a half-extracted
# tree is never visible under releases/<sha> and never becomes a build
# context. $$ keeps two concurrent attempts from sharing a scratch directory,
# even though the deploy workflow serialises them.
mkdir -p "$RELEASES"
STAGING="$RELEASES/.staging-$SHA.$$"
rm -rf "$STAGING"
mkdir -p "$STAGING"
cleanup() { rm -rf "$STAGING"; }
trap cleanup EXIT

tar -xzf "$ARCHIVE" -C "$STAGING" || die "could not unpack $ARCHIVE"

# --- sanity on what was unpacked ----------------------------------------
for required in \
    infra/production/docker-compose.yml \
    infra/production/deploy.sh \
    apps/api/Dockerfile \
    apps/web/Dockerfile; do
  [ -e "$STAGING/$required" ] || die "unpacked tree is missing $required — not a usable release"
done

# Secrets belong in shared/, never in a build context. make_release_archive.sh
# checks this before shipping; check it again on the receiving side, because
# the archive could have been placed in incoming/ by hand.
if leaked="$(find "$STAGING" -type f \( -name '.env' -o -name '.env.*' \) ! -name '*.example' -print)" \
   && [ -n "$leaked" ]; then
  echo "✗ the unpacked release contains secrets files:" >&2
  echo "$leaked" >&2
  die "refusing to build from a tree that carries secrets"
fi

# --- the environment file must already exist ----------------------------
# Fail here, before anything is switched, rather than half-way through a build.
ENV_FILE=""
for candidate in "${DRINKX_ENV_FILE:-}" "$DEPLOY_ROOT/shared/.env" "$DEPLOY_ROOT/infra/production/.env"; do
  if [ -n "$candidate" ] && [ -f "$candidate" ]; then ENV_FILE="$candidate"; break; fi
done
[ -n "$ENV_FILE" ] || die "no environment file found (looked for $DEPLOY_ROOT/shared/.env and the legacy $DEPLOY_ROOT/infra/production/.env)"
echo "✓ environment file: $ENV_FILE"

# --- publish ------------------------------------------------------------
# Re-releasing the same SHA must end with a clean tree, not a merge over
# whatever the previous attempt left. It used to get there by `rm -rf` on the
# old directory followed by `mv` — but after a successful deploy of that SHA
# `current -> releases/<sha>` points *into* the directory being removed, so
# between the two commands the pointer an operator follows dangles, and a
# failing `mv` leaves it dangling for good (REL-LOCAL-01).
#
# `git archive <sha>` piped through `gzip -n` is byte-for-byte reproducible,
# so the normal repeat preparation carries the archive that produced the tree
# already on disk. When that is the case there is nothing to replace: the
# directory is reused untouched and `current` never stops resolving. The
# archive's digest is recorded in releases/.markers/<sha> for that comparison;
# it lives outside the release directory because a build context must stay
# exactly the tree of its commit, and `ls` does not show it to the pruner.
MARKERS="$RELEASES/.markers"
mkdir -p "$MARKERS"
MARKER="$MARKERS/$SHA"

REUSE=0
if [ -e "$TARGET" ]; then
  if [ -f "$MARKER" ] && [ "$(tr -d ' \t\r\n' < "$MARKER")" = "$ARCHIVE_SHA" ]; then
    REUSE=1
    echo "✓ releases/$SHA was prepared from this exact archive — reusing it untouched"
  elif diff -r -q "$TARGET" "$STAGING" > /dev/null 2>&1; then
    # No marker: a tree prepared before this check existed, or by hand.
    # Comparing the content answers the same question, just slower.
    REUSE=1
    echo "✓ releases/$SHA already holds this exact tree — reusing it untouched"
  elif [ -L "$DEPLOY_ROOT/current" ] \
       && [ "$(cd "$DEPLOY_ROOT/current" 2>/dev/null && pwd -P || echo "")" \
            = "$(cd "$TARGET" && pwd -P)" ]; then
    # Same SHA, different tree, and it is the release serving traffic. That
    # cannot happen from `git archive` and is not worth guessing about:
    # replacing it would destroy the rollback target of a running release.
    die "releases/$SHA holds a different tree and 'current' points at it — refusing to replace the release that is serving traffic; move 'current' aside first if this is really what you want"
  fi
fi

if [ "$REUSE" -eq 1 ]; then
  # $STAGING is removed by the EXIT trap. Nothing under releases/ is touched.
  :
else
  # The published tree is made read-only so nothing can quietly accumulate in
  # a build context after the fact; undo that before replacing it.
  if [ -e "$TARGET" ]; then
    chmod -R u+w "$TARGET" 2>/dev/null || true
    rm -rf "$TARGET"
  fi
  mv "$STAGING" "$TARGET"
  trap - EXIT
  chmod -R a-w "$TARGET" 2>/dev/null || true
fi
printf '%s\n' "$ARCHIVE_SHA" > "$MARKER"

rm -f "$ARCHIVE" "$ARCHIVE.sha256"

# --- prune old releases --------------------------------------------------
# Keeps rollback material around without letting the disk grow forever. The
# release `current` points at is never removed, nor is the one just prepared.
CURRENT_TARGET=""
if [ -L "$DEPLOY_ROOT/current" ]; then
  CURRENT_TARGET="$(basename "$(readlink "$DEPLOY_ROOT/current")")"
fi
# shellcheck disable=SC2012  # names are 40-hex, ls -t is enough and portable
for old in $(ls -1t "$RELEASES" 2>/dev/null | tail -n +"$((KEEP_RELEASES + 1))"); do
  case "$old" in
    "$SHA" | "$CURRENT_TARGET" | .staging-*) continue ;;
  esac
  chmod -R u+w "$RELEASES/$old" 2>/dev/null || true
  rm -rf "$RELEASES/$old"
  rm -f "$MARKERS/$old"
  echo "  pruned old release $old"
done

echo "✓ release tree prepared"
echo "RELEASE_TREE=$TARGET"
echo "RELEASE_PREPARE=ok"

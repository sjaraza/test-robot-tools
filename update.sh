#!/usr/bin/env bash
# Pull the latest robot code and re-apply everything cheap. This is what the
# `update` alias runs, and it's meant to be run often.
#
#   bash ~/test-robot-tools/update.sh
#
# It pulls, then refreshes the splash screen, roboshine's import path and the
# aliases, and installs mosh if it's missing. It deliberately does NOT touch
# robot-hat, vilib or picar-x: those take 30-60 minutes and are handled by
# setup-picarx.sh. Nothing here needs sudo unless something actually changed.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

echo "updating $REPO_DIR ..."

BEFORE="$(git rev-parse --short HEAD 2>/dev/null || echo none)"

# --ff-only so a half-finished local edit fails loudly instead of creating a
# merge commit nobody asked for. -q because the object counts and diffstat are
# noise for a student; the before -> after line below says what matters.
if ! git pull --ff-only --quiet; then
  echo
  echo "Pull failed. Usually that means this robot has local edits." >&2
  echo "To throw them away and take the version from GitHub:" >&2
  echo >&2
  echo "    git -C $REPO_DIR reset --hard origin/main" >&2
  exit 1
fi

AFTER="$(git rev-parse --short HEAD)"

if [[ "$BEFORE" == "$AFTER" ]]; then
  echo "already up to date ($AFTER)"
else
  echo "updated $BEFORE -> $AFTER"
fi

# Re-run the installer so a changed splash, or roboshine's path, takes effect
# immediately.
bash "$REPO_DIR/install.sh"

# Aliases too: new ones get added as the tools grow, and a student who only ever
# runs `update` should still end up with them. It's a no-op when nothing changed.
bash "$REPO_DIR/setup-aliases.sh"

# mosh arrived after the first robots were set up, so check rather than assume.
if ! command -v mosh-server >/dev/null; then
  echo
  echo "mosh isn't installed yet -- adding it"
  bash "$REPO_DIR/setup-mosh.sh" || echo "mosh setup had trouble; carrying on" >&2
fi

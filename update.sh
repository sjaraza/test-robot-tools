#!/usr/bin/env bash
# Pull the latest robot code. This is what the `update` alias runs.
#
#   bash ~/test-robot-tools/update.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

echo "updating $REPO_DIR ..."

BEFORE="$(git rev-parse --short HEAD 2>/dev/null || echo none)"

# --ff-only so a half-finished local edit fails loudly instead of creating a
# merge commit nobody asked for.
if ! git pull --ff-only; then
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

# Re-run the installer so a changed splash or menu takes effect immediately.
bash "$REPO_DIR/install.sh"

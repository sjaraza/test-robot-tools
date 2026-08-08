#!/usr/bin/env bash
# Add the robot aliases to ~/.bashrc. Run this once, by hand:
#
#   bash ~/test-robot-tools/setup-aliases.sh
#
# Afterwards:
#   cockpit    take the controls (dashboard + menu)
#   robostat   print the robot's stats
#   update     pull the latest code from GitHub
#
# Safe to re-run. It rewrites its own managed block rather than appending, so
# repeated runs can't pile up duplicates, and it clears out the older `launch`
# alias if this robot still has one.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASHRC="$HOME/.bashrc"
BEGIN="# --- robot tools (managed by setup-aliases.sh) ---"
END="# --- end robot tools ---"

for script in robotmenu.py robostat.py update.sh; do
  if [[ ! -f "$REPO_DIR/$script" ]]; then
    echo "can't find $script in $REPO_DIR" >&2
    exit 1
  fi
done

chmod +x "$REPO_DIR"/robotmenu.py "$REPO_DIR"/robostat.py "$REPO_DIR"/*.sh

touch "$BASHRC"
cp "$BASHRC" "$BASHRC.bak.$(date +%Y%m%d%H%M%S)"

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

# Drop our managed block, plus any loose alias lines from earlier hand-editing
# (including the old `launch` name and the standalone robostat block).
awk -v b="$BEGIN" -v e="$END" '
  $0 == b { inblock = 1; next }
  $0 == e { inblock = 0; next }
  inblock { next }
  /^alias (cockpit|robostat|update|launch)=/ { next }
  /^# --- robot tools ---$/ { next }
  /^# --- robostat ---$/ { next }
  { print }
' "$BASHRC" > "$TMP"

# Collapse any trailing blank lines the removal left behind, then add the block.
{
  awk 'BEGIN{blank=0} {if ($0=="") {blank++} else {while(blank>0){print ""; blank--}; print}}' "$TMP"
  echo
  echo "$BEGIN"
  echo "alias cockpit='python3 $REPO_DIR/robotmenu.py'"
  echo "alias robostat='python3 $REPO_DIR/robostat.py'"
  echo "alias update='bash $REPO_DIR/update.sh'"
  echo "$END"
} > "$BASHRC"

echo "aliases written to $BASHRC"
echo "  (a backup of the previous file is alongside it)"
echo
echo "Run this once to use them in the current session:"
echo
echo "    source ~/.bashrc"
echo
echo "Then:  cockpit   robostat   update"

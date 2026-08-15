#!/usr/bin/env bash
# Add the robot aliases to ~/.bashrc. Run this once, by hand:
#
#   bash ~/test-robot-tools/setup-aliases.sh
#
# Afterwards:
#   cockpit    take the controls (dashboard + menu)
#   robostat   print the robot's stats
#   update     pull the latest code from GitHub
#   sb           re-read ~/.bashrc after editing it
#   eb           edit ~/.bashrc in vi
#   robotreboot  reboot the robot
#   robotoff     shut the robot down properly before unplugging it
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

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

# Drop our managed block, plus any loose alias lines from earlier hand-editing
# (including the old `launch` name and the standalone robostat block).
awk -v b="$BEGIN" -v e="$END" '
  $0 == b { inblock = 1; next }
  $0 == e { inblock = 0; next }
  inblock { next }
  /^alias (cockpit|robostat|update|launch|sb|eb|robotreboot|robotoff)=/ { next }
  /^# --- robot tools ---$/ { next }
  /^# --- robostat ---$/ { next }
  { print }
' "$BASHRC" > "$TMP"

# Build the new file, then only replace ~/.bashrc if it actually differs.
# Students are told to run `update` often, and a backup file per run -- plus a
# rewritten .bashrc that changed nothing -- would be pure noise.
NEW="$(mktemp)"
trap 'rm -f "$TMP" "$NEW"' EXIT
{
  awk 'BEGIN{blank=0} {if ($0=="") {blank++} else {while(blank>0){print ""; blank--}; print}}' "$TMP"
  echo
  echo "$BEGIN"
  echo "alias cockpit='python3 $REPO_DIR/robotmenu.py'"
  echo "alias robostat='python3 $REPO_DIR/robostat.py'"
  # Deliberately setup-all.sh, not update.sh: it works out what's missing and
  # installs only that, so one command covers both a fresh robot and picking up
  # changes later. On a set-up robot it finishes in seconds.
  echo "alias update='bash $REPO_DIR/setup-all.sh --yes'"
  echo "alias sb='source ~/.bashrc'"
  echo "alias eb='vi ~/.bashrc'"
  echo "alias robotreboot='sudo systemctl reboot'"
  echo "alias robotoff='sudo systemctl poweroff'"
  echo "$END"
} > "$NEW"

if cmp -s "$NEW" "$BASHRC"; then
  echo "aliases already up to date"
  exit 0
fi

cp "$BASHRC" "$BASHRC.robotbak"        # one backup, overwritten, not one per run
cat "$NEW" > "$BASHRC"

echo "aliases written to $BASHRC"
echo "  (previous version saved as ~/.bashrc.robotbak)"
echo
echo "Run this once to use them in the current session:"
echo
echo "    source ~/.bashrc"
echo
echo "Then:  cockpit  robostat  update  sb  eb  robotreboot  robotoff"

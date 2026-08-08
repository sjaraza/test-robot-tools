#!/usr/bin/env bash
# Set up this robot. Run once per robot, after cloning the repo.
#
#   bash ~/test-robot-tools/install.sh
#
# Installs the login splash into /etc/motd and makes the menu executable.
# Safe to re-run; update.sh calls it after every pull.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MENU="$REPO_DIR/robotmenu.py"

if [[ ! -f "$MENU" ]]; then
  echo "can't find robotmenu.py next to install.sh" >&2
  exit 1
fi

chmod +x "$MENU"

# PiCar-X and robot-hat keep calibration data under /opt, root-owned after a
# fresh install. Without this, creating Picarx() dies with
# "PermissionError: [Errno 13] ... '/opt/picar-x'".
for dir in /opt/picar-x /opt/robot-hat; do
  if [[ -d "$dir" ]]; then
    if [[ ! -w "$dir" ]]; then
      echo "taking ownership of $dir ..."
      sudo chown -R "$USER":"$USER" "$dir"
    fi
  fi
done

# The splash is generated rather than hardcoded, so each robot shows its own
# hostname and there's only one copy of the block-letter font. --color is
# required here: stdout is a pipe into tee, not a terminal, so colour would
# otherwise be stripped out of the motd.
echo "writing /etc/motd ..."
python3 "$MENU" --splash --color | sudo tee /etc/motd >/dev/null

echo
echo "Installed. Add these two lines to ~/.bashrc if they aren't there yet:"
echo
echo "    alias launch='python3 $MENU'"
echo "    alias update='bash $REPO_DIR/update.sh'"
echo
echo "Then:  source ~/.bashrc"
echo
echo "Log out and back in to see the splash screen."

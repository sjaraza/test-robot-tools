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

# picar-x and robot-hat live in the home directory on these robots.
for dir in "$HOME/picar-x" "$HOME/robot-hat"; do
  if [[ -d "$dir" && ! -w "$dir" ]]; then
    echo "taking ownership of $dir ..."
    sudo chown -R "$USER":"$USER" "$dir"
  fi
done

# Separately from where the source lives, picarx writes its servo calibration to
# a path hardcoded as /opt/picar-x. On a fresh robot that directory doesn't
# exist and /opt is root-owned, so Picarx() fails with
# "PermissionError: [Errno 13] ... '/opt/picar-x'" -- errno 13 on a missing path
# because the refusal is on the parent. Confirmed on robot-1. Create and hand
# over, or every student hits it on their first menu action.
if [[ ! -d /opt/picar-x ]]; then
  echo "creating /opt/picar-x (picarx writes its calibration there) ..."
  sudo mkdir -p /opt/picar-x
fi
if [[ ! -w /opt/picar-x ]]; then
  echo "taking ownership of /opt/picar-x ..."
  sudo chown -R "$USER":"$USER" /opt/picar-x
fi

# The splash is generated rather than hardcoded, so each robot shows its own
# hostname and there's only one copy of the block-letter font. --color is
# required here: stdout is a pipe into tee, not a terminal, so colour would
# otherwise be stripped out of the motd.
echo "writing /etc/motd ..."
python3 "$MENU" --splash --color | sudo tee /etc/motd >/dev/null

# update.sh re-runs this on every pull, so only nag about aliases when they're
# actually missing. Otherwise this block is pure clutter several times a day.
if grep -q "alias cockpit=" "$HOME/.bashrc" 2>/dev/null; then
  echo "done"
else
  echo
  echo "Installed. One more step -- add the aliases:"
  echo
  echo "    bash $REPO_DIR/setup-aliases.sh"
  echo "    source ~/.bashrc"
  echo
  echo "That gives you:  cockpit   robostat   update"
  echo
  echo "Log out and back in to see the splash screen."
fi

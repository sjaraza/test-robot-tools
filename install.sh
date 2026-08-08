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

# The splash is generated rather than hardcoded, so each robot shows its own
# hostname and there's only one copy of the block-letter font. --color is
# required here: stdout is a pipe into tee, not a terminal, so colour would
# otherwise be stripped out of the motd.
echo "writing /etc/motd ..."
python3 "$MENU" --splash --color | sudo tee /etc/motd >/dev/null

echo
echo "Installed. Now add the aliases (once per robot):"
echo
echo "    bash $REPO_DIR/setup-aliases.sh"
echo "    source ~/.bashrc"
echo
echo "That gives you:  cockpit   robostat   update"
echo
echo "Log out and back in to see the splash screen."

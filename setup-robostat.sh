#!/usr/bin/env bash
# Add the `robostat` alias to ~/.bashrc. Run this once, by hand:
#
#   bash ~/test-robot-tools/setup-robostat.sh
#
# Afterwards, typing `robostat` prints the robot's stats.
# Safe to re-run -- it won't add a duplicate line.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$REPO_DIR/robostat.py"
BASHRC="$HOME/.bashrc"

if [[ ! -f "$SCRIPT" ]]; then
  echo "can't find robostat.py next to this script" >&2
  exit 1
fi

chmod +x "$SCRIPT"

if grep -q "alias robostat=" "$BASHRC" 2>/dev/null; then
  echo "robostat alias is already in $BASHRC -- nothing to do"
else
  cat >> "$BASHRC" <<EOF

# --- robostat ---
alias robostat='python3 $SCRIPT'
EOF
  echo "added the robostat alias to $BASHRC"
fi

echo
echo "Run this once to use it in the current session:"
echo
echo "    source ~/.bashrc"
echo
echo "Then:"
echo
echo "    robostat            one snapshot"
echo "    robostat --watch    keep refreshing"

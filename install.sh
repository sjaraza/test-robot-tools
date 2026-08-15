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

# Make `import roboshine` work from any directory, without installing anything.
# A .pth file in the user's site-packages just adds this repo to Python's path,
# so `update` keeps the library current with no reinstall step -- which pip
# install would have required after every pull.
# An SSH login runs bash as a *login* shell, which does NOT read ~/.bashrc. It
# reads the FIRST of ~/.bash_profile, ~/.bash_login, ~/.profile that exists and
# ignores the others -- so writing to ~/.profile does nothing on a robot that has
# a ~/.bash_profile. Find the file bash will actually use.
echo "setting up the login greeting ..."
LOGIN_FILE=""
for candidate in "$HOME/.bash_profile" "$HOME/.bash_login" "$HOME/.profile"; do
  if [[ -f "$candidate" ]]; then
    LOGIN_FILE="$candidate"
    break
  fi
done
LOGIN_FILE="${LOGIN_FILE:-$HOME/.profile}"      # none existed; create .profile
touch "$LOGIN_FILE"

LOGIN_BEGIN="# --- robot tools login (managed by install.sh) ---"
LOGIN_END="# --- end robot tools login ---"

# A managed block, rewritten each time, so additions reach robots that already
# ran an older version of this script. The earlier ad-hoc version had no markers,
# so strip that shape too.
LOGIN_TMP="$(mktemp)"
LOGIN_NEW="$(mktemp)"
trap 'rm -f "$LOGIN_TMP" "$LOGIN_NEW" "${NEW_MOTD:-}"' EXIT

awk -v b="$LOGIN_BEGIN" -v e="$LOGIN_END" '
  $0 == b { inblock = 1; next }
  $0 == e { inblock = 0; next }
  inblock { next }
  # the older, marker-less block: a comment plus three lines
  /^# --- robot tools: make login shells read ~\/\.bashrc ---$/ { skip = 3; next }
  skip > 0 { skip--; next }
  { print }
' "$LOGIN_FILE" > "$LOGIN_TMP"

{
  cat "$LOGIN_TMP"
  echo
  echo "$LOGIN_BEGIN"
  echo 'if [ -n "$BASH_VERSION" ] && [ -f "$HOME/.bashrc" ]; then'
  echo '  . "$HOME/.bashrc"'
  echo 'fi'
  echo '# Show the robot vitals on login. Interactive shells only: printing here'
  echo '# during an scp or sftp transfer would corrupt it.'
  echo 'case $- in'
  echo "  *i*) [ -f \"$REPO_DIR/robostat.py\" ] && python3 \"$REPO_DIR/robostat.py\" 2>/dev/null ;;"
  echo 'esac'
  echo "$LOGIN_END"
} > "$LOGIN_NEW"

if cmp -s "$LOGIN_NEW" "$LOGIN_FILE"; then
  echo "  $(basename "$LOGIN_FILE") already set up"
else
  cat "$LOGIN_NEW" > "$LOGIN_FILE"
  echo "  $(basename "$LOGIN_FILE") sources ~/.bashrc and shows robostat at login"
fi

echo "making roboshine importable ..."
SITE="$(python3 -c 'import site; print(site.getusersitepackages())' 2>/dev/null || true)"
if [[ -n "$SITE" ]]; then
  mkdir -p "$SITE"
  echo "$REPO_DIR" > "$SITE/roboshine.pth"
  if python3 -c "import roboshine" 2>/dev/null; then
    echo "  import roboshine works from anywhere"
  else
    echo "  WARNING: wrote $SITE/roboshine.pth but the import still fails" >&2
  fi
else
  echo "  WARNING: couldn't find your site-packages; roboshine won't import" >&2
fi

# The splash is generated rather than hardcoded, so each robot shows its own
# hostname and there's only one copy of the block-letter font. --color is
# required here: stdout is a pipe into tee, not a terminal, so colour would
# otherwise be stripped out of the motd.
# Only write it if it differs. Writing needs sudo, and students run `update`
# often -- a password prompt on every run for a file that didn't change is the
# kind of friction that stops people updating at all.
NEW_MOTD="$(mktemp)"
trap 'rm -f "$NEW_MOTD"' EXIT
python3 "$MENU" --splash --color > "$NEW_MOTD"
if cmp -s "$NEW_MOTD" /etc/motd 2>/dev/null; then
  echo "splash screen already current"
else
  echo "writing /etc/motd ..."
  sudo tee /etc/motd < "$NEW_MOTD" >/dev/null
fi

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

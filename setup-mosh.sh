#!/usr/bin/env bash
# Install mosh on this robot. Run on the robot, over SSH:
#
#   bash ~/test-robot-tools/setup-mosh.sh
#
# mosh replaces ssh for interactive work and is a real improvement on a
# congested 2.4GHz AP: it echoes your keystrokes locally instead of waiting for
# a round trip, and the session survives WiFi dropouts, roaming and closing the
# laptop lid. The cockpit's full-screen redraws feel much better over it.
#
# It has to be installed on BOTH ends -- here, and on the laptop or VM.
# Then connect with:  mosh robot@robot-1.local
#
# Safe to re-run.

set -uo pipefail

BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; OFF=$'\033[0m'
ok()   { echo "  ${GREEN}ok${OFF}   $*"; }
warn() { echo "  ${YELLOW}!${OFF}    $*"; }

[[ $EUID -eq 0 ]] && { echo "run as the normal user, not with sudo" >&2; exit 1; }

echo "${BOLD}Installing mosh on $(hostname)${OFF}"
echo

if command -v mosh-server >/dev/null; then
  ok "already installed: $(mosh-server --version 2>&1 | head -1)"
else
  sudo apt-get update -qq || warn "apt update had trouble, trying anyway"
  if sudo apt-get install -y mosh; then
    ok "installed: $(mosh-server --version 2>&1 | head -1)"
  else
    echo "  ${RED}fail${OFF} couldn't install mosh" >&2
    exit 1
  fi
fi

# --- the locale trap -------------------------------------------------------
# mosh insists on a UTF-8 locale and refuses to start without one. This robot
# has had exactly that problem before: LANG was set to a locale that had never
# been generated, which produced "cannot change locale" warnings on every login.
echo
echo "${BOLD}Checking the locale${OFF}  (mosh requires UTF-8)"

if locale 2>&1 >/dev/null | grep -q "Cannot set"; then
  warn "the locale is broken -- mosh will refuse to start"
  echo
  echo "  Fix it with either of these:"
  echo
  echo "    sudo sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen"
  echo "    sudo locale-gen en_US.UTF-8"
  echo "    sudo update-locale LANG=en_US.UTF-8"
  echo
  echo "  or take the always-present fallback, which needs nothing generated:"
  echo
  echo "    sudo update-locale LANG=C.UTF-8"
  echo
  echo "  Then log out and back in."
else
  CHARMAP="$(locale charmap 2>/dev/null || echo unknown)"
  if [[ "$CHARMAP" == "UTF-8" ]]; then
    ok "locale is UTF-8 (${LANG:-unset})"
  else
    warn "character map is '$CHARMAP', not UTF-8 -- mosh may refuse"
    warn "set one with: sudo update-locale LANG=C.UTF-8"
  fi
fi

# --- firewall / ports ------------------------------------------------------
# mosh uses UDP 60000-61000 for the session itself, after authenticating over
# ssh. On a flat LAN behind your own AP there's nothing to open, but it's worth
# knowing if you ever put a firewall between laptop and robot.
echo
echo "${BOLD}Ports${OFF}"
if command -v ufw >/dev/null && sudo ufw status 2>/dev/null | grep -q "^Status: active"; then
  warn "ufw is active -- allow mosh with: sudo ufw allow 60000:61000/udp"
else
  ok "no active firewall here; mosh needs UDP 60000-61000 between the two ends"
fi

cat <<EOF

${GREEN}${BOLD}Done.${OFF}

Install mosh on your laptop too, then connect with:

    mosh robot@$(hostname).local

  Ubuntu / the VM :  sudo apt install mosh
  macOS           :  brew install mosh
  Windows         :  use WSL, or stay with ssh

If mosh can't connect but ssh can, it's almost always one of: mosh missing on
the other end, a broken locale (above), or UDP being blocked.
EOF

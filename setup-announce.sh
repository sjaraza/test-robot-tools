#!/usr/bin/env bash
# Make the robot say its name and IP address out loud every time it boots.
#
#   bash ~/test-robot-tools/setup-announce.sh
#
# Installs espeak-ng and a systemd service that runs announce.sh once the network
# is up. Useful when twenty identical robots are on a table and you need to know
# which one just came back.
#
#   --remove   turn it off again
#
# Safe to re-run. Needs the speaker working -- run ~/robot-hat/i2samp.sh first if
# you haven't.

set -uo pipefail

BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; OFF=$'\033[0m'
ok()   { echo "  ${GREEN}ok${OFF}   $*"; }
warn() { echo "  ${YELLOW}!${OFF}    $*"; }
die()  { echo "  ${RED}fail${OFF} $*" >&2; exit 1; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT=/etc/systemd/system/roboshine-announce.service
SCRIPT="$REPO_DIR/announce.sh"

[[ $EUID -eq 0 ]] && die "run as the normal user, not with sudo"

if [[ "${1:-}" == "--remove" ]]; then
  echo "${BOLD}Turning off the boot announcement${OFF}"
  sudo systemctl disable --now roboshine-announce.service 2>/dev/null || true
  sudo rm -f "$UNIT"
  sudo systemctl daemon-reload
  ok "removed"
  exit 0
fi

echo "${BOLD}Boot announcement for $(hostname)${OFF}"
echo

[[ -f "$SCRIPT" ]] || die "can't find $SCRIPT"

# --- espeak-ng -------------------------------------------------------------
if command -v espeak-ng >/dev/null; then
  ok "espeak-ng already installed"
else
  sudo apt-get update -qq || warn "apt update had trouble, trying anyway"
  sudo apt-get install -y espeak-ng || die "couldn't install espeak-ng"
  ok "espeak-ng installed (about 1MB, and it speaks in well under a second)"
fi

# --- is there a speaker at all? -------------------------------------------
if [[ -e /proc/asound/cards ]] && grep -qv "no soundcards" /proc/asound/cards 2>/dev/null \
   && [[ -s /proc/asound/cards ]]; then
  ok "a sound card is present:"
  sed 's/^/       /' /proc/asound/cards | head -4
else
  warn "no sound card found -- set the amplifier up first:"
  warn "  cd ~/robot-hat && sudo bash i2samp.sh"
  warn "installing the service anyway; it will start working once sound does"
fi

# --- the service -----------------------------------------------------------
# Runs as the login user, not root: audio devices belong to the audio group and
# root has no reason to be involved. Type=oneshot with After/Wants on
# network-online so there's an address to read out; announce.sh also waits on its
# own, because "online" and "has an IP" aren't quite the same thing on WiFi.
sudo tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=Say this robot's name and IP address at boot
After=network-online.target sound.target
Wants=network-online.target

[Service]
Type=oneshot
User=$USER
Group=$(id -gn)
ExecStart=/bin/bash $SCRIPT
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable roboshine-announce.service >/dev/null 2>&1 \
  && ok "enabled -- it will speak on every boot" \
  || die "couldn't enable the service"

echo
read -r -p "Say it now, to test the speaker? [Y/n]: " reply
if [[ ! "$reply" =~ ^[Nn] ]]; then
  echo
  bash "$SCRIPT"
fi

cat <<EOF

${GREEN}${BOLD}Done.${OFF}

  hear it now          bash $SCRIPT
  see what it did      journalctl -u roboshine-announce -b
  turn it off          bash $REPO_DIR/setup-announce.sh --remove
EOF

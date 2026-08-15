#!/usr/bin/env bash
# One command to take a freshly imaged robot all the way to a working cockpit.
#
# On the robot, over SSH:
#
#   curl -fsSL https://raw.githubusercontent.com/sjaraza/test-robot-tools/main/setup-all.sh | bash
#
# or, if you've already cloned the repo:
#
#   bash ~/test-robot-tools/setup-all.sh
#
# Use it for a fresh robot AND for picking up changes later -- it works out
# what's already there and only does the rest. On a robot that's fully set up it
# finishes in seconds and installs nothing.
#
# It checks, in order:
#   1. this repo                        clone, or pull
#   2. robot-hat, vilib, picar-x        install only the ones missing
#   3. splash, roboshine path, aliases  always refreshed, all cheap
#   4. mosh                             install if missing
#
# Options are passed through to setup-picarx.sh:
#   --skip-libs       the PiCar-X software is already installed, skip step 2
#   --skip-upgrade    don't run 'apt upgrade' (much faster)
#   --with-sound      also set up the I2S amplifier
#   --yes             don't ask for confirmation
#
# Safe to re-run.

set -uo pipefail

REPO_URL="https://github.com/sjaraza/test-robot-tools.git"
REPO_DIR="$HOME/test-robot-tools"
SKIP_LIBS=0
PASS_THROUGH=()

for arg in "$@"; do
  case "$arg" in
    --skip-libs) SKIP_LIBS=1 ;;
    -h|--help)
      awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"
      exit 0 ;;
    *) PASS_THROUGH+=("$arg") ;;
  esac
done

BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; OFF=$'\033[0m'

say()  { echo; echo "${BOLD}$*${OFF}"; }
ok()   { echo "  ${GREEN}ok${OFF}  $*"; }
die()  { echo "  ${RED}fail${OFF} $*" >&2; exit 1; }

if [[ $EUID -eq 0 ]]; then
  die "run this as the normal user, not with sudo -- it calls sudo itself"
fi

say "Setting up $(hostname)"

# --- 1. the repo -----------------------------------------------------------
# This script may be running straight from a pipe (curl | bash), in which case
# there's no repo yet, or from inside an existing checkout.
say "1. Getting the robot tools"
if [[ -d "$REPO_DIR/.git" ]]; then
  git -C "$REPO_DIR" pull --ff-only --quiet \
    && ok "updated $REPO_DIR" \
    || echo "  ${YELLOW}!${OFF}   couldn't fast-forward, using what's there"
else
  command -v git >/dev/null || sudo apt-get install -y git || die "couldn't install git"
  git clone --quiet "$REPO_URL" "$REPO_DIR" || die "clone failed"
  ok "cloned to $REPO_DIR"
fi

# --- 2. the PiCar-X software ----------------------------------------------
# Check each library separately and report it, so a student can see what this
# run is actually going to do before it spends half an hour doing it.
say "2. PiCar-X software"

MISSING=()
for pair in "robot_hat:robot-hat" "vilib:vilib" "picarx:picar-x"; do
  module="${pair%%:*}"
  label="${pair##*:}"
  if python3 -c "import $module" 2>/dev/null; then
    ok "$label"
  else
    echo "  ${YELLOW}--${OFF}   $label is missing"
    MISSING+=("$label")
  fi
done

if (( SKIP_LIBS )); then
  echo "  skipped (--skip-libs)"
elif (( ${#MISSING[@]} == 0 )); then
  ok "nothing to install"
else
  echo
  echo "  Installing: ${MISSING[*]}"
  echo "  ${YELLOW}This can take 30-60 minutes. Leave the window open.${OFF}"
  # setup-picarx.sh checks each library itself too, so the ones already present
  # are skipped rather than rebuilt.
  bash "$REPO_DIR/setup-picarx.sh" "${PASS_THROUGH[@]+"${PASS_THROUGH[@]}"}" \
    || die "PiCar-X install failed -- see ~/picarx-install.log"
fi

# --- 3. everything else ----------------------------------------------------
# Delegated to update.sh rather than repeated here: splash, roboshine's import
# path, aliases and mosh. One code path, so the two scripts can't drift apart.
# All of it is cheap and needs no sudo unless something genuinely changed.
say "3. Splash, roboshine, aliases, mosh"
bash "$REPO_DIR/update.sh" || die "update.sh failed"

# ---------------------------------------------------------------------------
echo
if (( ${#MISSING[@]} )); then
  echo "${GREEN}${BOLD}Done -- installed: ${MISSING[*]}${OFF}"
  echo
  echo "Reboot before using the hardware:   ${BOLD}robotreboot${OFF}"
else
  echo "${GREEN}${BOLD}Done -- everything was already installed, just updated.${OFF}"
fi
echo
echo "You can type:"
echo "    ${BOLD}cockpit${OFF}     drive the robot"
echo "    ${BOLD}robostat${OFF}    battery, temperature, WiFi"
echo "    ${BOLD}update${OFF}      get the latest version of these tools"
echo "    ${BOLD}robotoff${OFF}    shut down properly before unplugging"
echo
echo "Optional, needs the speaker working:"
echo "    bash $REPO_DIR/setup-announce.sh    say name and IP at every boot"

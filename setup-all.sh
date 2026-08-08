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
# It runs, in order:
#   1. clone or update this repo
#   2. setup-picarx.sh   -- robot-hat, vilib, picar-x  (the slow part)
#   3. install.sh        -- the login splash screen
#   4. setup-aliases.sh  -- the cockpit / robostat / update aliases
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
say "2. PiCar-X software"
if (( SKIP_LIBS )); then
  echo "  skipped (--skip-libs)"
elif python3 -c "import picarx, robot_hat, vilib" 2>/dev/null; then
  ok "already installed"
else
  bash "$REPO_DIR/setup-picarx.sh" "${PASS_THROUGH[@]+"${PASS_THROUGH[@]}"}" \
    || die "PiCar-X install failed -- see ~/picarx-install.log"
fi

# --- 3. splash screen ------------------------------------------------------
say "3. Login splash screen"
bash "$REPO_DIR/install.sh" || die "install.sh failed"

# --- 4. aliases ------------------------------------------------------------
say "4. Aliases"
bash "$REPO_DIR/setup-aliases.sh" || die "setup-aliases.sh failed"

# ---------------------------------------------------------------------------
echo
echo "${GREEN}${BOLD}Done.${OFF}"
echo
echo "Reboot, then log back in to see the splash screen:"
echo
echo "    sudo reboot"
echo
echo "After that you can type:"
echo "    ${BOLD}cockpit${OFF}     drive the robot"
echo "    ${BOLD}robostat${OFF}    battery, temperature, WiFi"
echo "    ${BOLD}update${OFF}      get the latest version of these tools"

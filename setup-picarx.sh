#!/usr/bin/env bash
# Install the whole SunFounder PiCar-X software stack on a robot, in one go.
#
# Run this ON THE ROBOT, over SSH, as the normal user (not root):
#
#   bash ~/test-robot-tools/setup-picarx.sh
#
# Options:
#   --skip-upgrade    don't run 'apt upgrade' (much faster; the slowest step)
#   --with-sound      also run robot-hat's i2samp.sh for the I2S amplifier
#   --yes             don't ask for confirmation before starting
#
# Safe to re-run. Existing checkouts are updated rather than re-cloned, and each
# step reports whether it did anything.
#
# This takes a while on a Pi Zero 2 W -- 30 to 60 minutes with the upgrade, and
# vilib pulls in OpenCV which is the single longest part. Everything is logged to
# ~/picarx-install.log so a failure can be read after the fact.

set -uo pipefail

LOG="$HOME/picarx-install.log"
SKIP_UPGRADE=0
WITH_SOUND=0
ASSUME_YES=0

for arg in "$@"; do
  case "$arg" in
    --skip-upgrade) SKIP_UPGRADE=1 ;;
    --with-sound)   WITH_SOUND=1 ;;
    --yes|-y)       ASSUME_YES=1 ;;
    -h|--help)
      # Print the header comment, stopping at the first non-comment line.
      awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"
      exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 1 ;;
  esac
done

# Everything below is echoed to the terminal and appended to the log.
exec > >(tee -a "$LOG") 2>&1

BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; OFF=$'\033[0m'
STEP=0
STARTED=$SECONDS

step() {
  STEP=$((STEP + 1))
  echo
  echo "${BOLD}== $STEP. $* ==${OFF}"
}

ok()   { echo "   ${GREEN}ok${OFF}  $*"; }
warn() { echo "   ${YELLOW}!${OFF}   $*"; }
die()  { echo "   ${RED}fail${OFF} $*"; echo; echo "See $LOG"; exit 1; }

elapsed() {
  local total=$((SECONDS - STARTED))
  printf '%dm%02ds' $((total / 60)) $((total % 60))
}

# Clone if absent, otherwise update. Returns 0 either way.
fetch_repo() {
  local url="$1" dir="$2" branch="${3:-}"
  if [[ -d "$dir/.git" ]]; then
    echo "   updating $dir"
    git -C "$dir" pull --ff-only --quiet || warn "couldn't fast-forward $dir, using what's there"
  else
    echo "   cloning $url"
    if [[ -n "$branch" ]]; then
      git clone -b "$branch" "$url" "$dir" --depth 1 --quiet || die "clone failed: $url"
    else
      git clone "$url" "$dir" --depth 1 --quiet || die "clone failed: $url"
    fi
  fi
}

# ---------------------------------------------------------------------------

echo "${BOLD}PiCar-X software install${OFF}   $(date 2>/dev/null || echo '(no clock)')"
echo "log: $LOG"

if [[ $EUID -eq 0 ]]; then
  die "run this as the normal user, not with sudo -- it calls sudo itself"
fi

step "Checking the basics"

sudo -v 2>/dev/null || die "sudo isn't working for this user"
ok "sudo works"

if ! ping -c1 -W3 github.com >/dev/null 2>&1 && ! curl -fsS -m5 -o /dev/null https://github.com; then
  die "can't reach github.com -- check the robot's internet connection"
fi
ok "github.com reachable"

# A Zero 2 W has no battery-backed clock. A wrong date makes apt reject the
# repository metadata as "not valid yet", which is confusing to debug.
YEAR=$(date +%Y 2>/dev/null || echo 1970)
if (( YEAR < 2024 )); then
  warn "system clock reads $YEAR -- apt may reject repository metadata"
  warn "fix with: sudo timedatectl set-ntp true"
fi

AVAIL_MB=$(df -m --output=avail / 2>/dev/null | tail -1 | tr -d ' ')
if [[ -n "$AVAIL_MB" ]] && (( AVAIL_MB < 2048 )); then
  warn "only ${AVAIL_MB}MB free on / -- OpenCV alone wants over a gigabyte"
else
  ok "${AVAIL_MB:-?}MB free on /"
fi

if (( ! ASSUME_YES )); then
  echo
  echo "This installs robot-hat, vilib and picar-x, and takes 30-60 minutes."
  read -r -p "Continue? [y/N]: " reply
  [[ "$reply" =~ ^[Yy] ]] || { echo "cancelled"; exit 0; }
fi

# ---------------------------------------------------------------------------

step "System packages"

export DEBIAN_FRONTEND=noninteractive
APT_OPTS=(-y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)

sudo apt-get update || die "apt update failed"
ok "package lists updated"

if (( SKIP_UPGRADE )); then
  warn "skipping apt upgrade (--skip-upgrade)"
else
  echo "   upgrading installed packages, this is the slow part"
  sudo apt-get "${APT_OPTS[@]}" upgrade || die "apt upgrade failed"
  ok "system upgraded"
fi

# python3-dev and i2c-tools aren't in SunFounder's list but the builds want the
# former and i2cdetect is how you check the hat is actually on the bus.
sudo apt-get "${APT_OPTS[@]}" install \
  git python3-pip python3-setuptools python3-smbus python3-dev i2c-tools \
  || die "installing base packages failed"
ok "git, pip, setuptools, smbus, python3-dev, i2c-tools"

# ---------------------------------------------------------------------------

step "robot-hat"
cd "$HOME" || die "no home directory?"
fetch_repo https://github.com/sunfounder/robot-hat.git "$HOME/robot-hat" 2.5.x
( cd "$HOME/robot-hat" && sudo python3 install.py ) || die "robot-hat install.py failed"
ok "robot-hat installed"

# ---------------------------------------------------------------------------

step "vilib  (pulls in OpenCV, the longest step)"
cd "$HOME" || exit 1
fetch_repo https://github.com/sunfounder/vilib.git "$HOME/vilib"
( cd "$HOME/vilib" && sudo python3 install.py ) || die "vilib install.py failed"
ok "vilib installed"

# ---------------------------------------------------------------------------

step "picar-x"
cd "$HOME" || exit 1
fetch_repo https://github.com/sunfounder/picar-x.git "$HOME/picar-x" 2.1.x
cd "$HOME/picar-x" || exit 1

# Debian trixie marks the system Python as externally managed (PEP 668), so pip
# refuses to install into it without --break-system-packages. Older pip doesn't
# know that flag, hence the fallback.
if sudo pip3 install . --break-system-packages; then
  ok "picar-x installed"
elif sudo pip3 install .; then
  ok "picar-x installed (pip without --break-system-packages)"
else
  die "pip install of picar-x failed"
fi

# ---------------------------------------------------------------------------

step "Calibration directory"
# picarx writes its servo calibration to a hardcoded /opt/picar-x. On a fresh
# system that directory doesn't exist and /opt is root-owned, so creating a
# Picarx() object dies with PermissionError [Errno 13] -- errno 13 on a path that
# doesn't exist, because the refusal comes from the parent.
if [[ ! -d /opt/picar-x ]]; then
  sudo mkdir -p /opt/picar-x && ok "created /opt/picar-x"
fi
if [[ ! -w /opt/picar-x ]]; then
  sudo chown -R "$USER":"$USER" /opt/picar-x && ok "/opt/picar-x is yours"
else
  ok "/opt/picar-x already writable"
fi

# ---------------------------------------------------------------------------

step "Checking it worked"

for module in robot_hat vilib picarx; do
  if python3 -c "import $module" 2>/dev/null; then
    ok "import $module"
  else
    warn "import $module FAILED"
    FAILED=1
  fi
done

if command -v i2cdetect >/dev/null; then
  echo "   I2C bus 1:"
  sudo i2cdetect -y 1 2>/dev/null | sed 's/^/     /' || warn "i2cdetect failed"
fi

# ---------------------------------------------------------------------------

if (( WITH_SOUND )); then
  step "Sound (I2S amplifier)"
  if [[ ! -t 0 ]]; then
    warn "i2samp.sh asks questions and stdin isn't a terminal -- skipping"
    warn "run it yourself later: cd ~/robot-hat && sudo bash i2samp.sh"
  else
    echo "   ${YELLOW}i2samp.sh will ask you some questions.${OFF}"
    echo "   ${YELLOW}Answer N when it offers to reboot -- do that yourself after.${OFF}"
    echo
    ( cd "$HOME/robot-hat" && sudo bash i2samp.sh ) || warn "i2samp.sh reported a problem"
  fi
else
  step "Sound (I2S amplifier)"
  warn "skipped. Add --with-sound, or run it later:"
  warn "  cd ~/robot-hat && sudo bash i2samp.sh"
fi

# ---------------------------------------------------------------------------

echo
if [[ -n "${FAILED:-}" ]]; then
  echo "${YELLOW}${BOLD}Finished in $(elapsed), but some imports failed.${OFF}"
  echo "Look in $LOG for the step that went wrong."
  exit 1
fi

echo "${GREEN}${BOLD}Done in $(elapsed).${OFF}"
echo
echo "Reboot before using the hardware:  sudo reboot"
echo "Then check everything with:        python3 ~/test-robot-tools/robotmenu.py --probe"

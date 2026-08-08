#!/usr/bin/env bash
# Prepare THIS robot to become the golden image. Run on robot-1, over SSH:
#
#   sudo bash ~/test-robot-tools/golden-card/prepare-golden.sh
#
# Then shut down, image the card, flash the clones, and stamp each one with
# stamp-card.py from your Mac.
#
# What this does is strip per-machine identity so it isn't cloned nineteen times,
# and reset cloud-init so every clone runs its first-boot customisation properly.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "run this with sudo" >&2
  exit 1
fi

THIS_HOST="$(hostname)"
echo "preparing $THIS_HOST as the golden image"
echo

echo "== clearing state that must not be cloned =="

# machine-id: twenty clones sharing one makes them look like the same host to
# DHCP and systemd. An empty file is regenerated on next boot.
: > /etc/machine-id
rm -f /var/lib/dbus/machine-id
echo "  machine-id cleared"

# SSH host keys. cloud-init regenerates these for a new instance-id anyway, but
# clearing them means the image itself carries no host identity.
rm -f /etc/ssh/ssh_host_*
echo "  SSH host keys removed"

apt-get clean || true
rm -rf /var/log/journal/* /var/log/*.gz /var/log/*.[0-9] 2>/dev/null || true
rm -f /tmp/robotcam.* 2>/dev/null || true
echo "  logs, apt cache and stream leftovers cleared"

for home in /home/*; do
  rm -f "$home/.bash_history" "$home/.viminfo" "$home/.bashrc.bak."* 2>/dev/null || true
  rm -f "$home/.ssh/known_hosts" 2>/dev/null || true
done
echo "  per-user history and known_hosts cleared"

echo
echo "== resetting cloud-init =="
# Without this, cloud-init on a clone may decide it has already run. Combined
# with a fresh instance-id per card (stamp-card.py sets that), every clone
# applies its own hostname and network config from the boot partition.
#
# Deliberately NOT using --configs, so the generated netplan config stays put
# and this robot still has WiFi if you boot it again before imaging.
cloud-init clean --logs
echo "  cloud-init state cleared"

echo
echo "Golden image is ready. Next:"
echo
echo "  1.  sudo shutdown -h now"
echo "  2.  move the card to your Mac and make an image of it:"
echo "        diskutil list                     # find the disk number"
echo "        diskutil unmountDisk /dev/diskN"
echo "        sudo dd if=/dev/rdiskN of=~/robot-golden.img bs=4m status=progress"
echo "  3.  flash ~/robot-golden.img to each card (balenaEtcher or dd)"
echo "  4.  stamp each card, on the Mac:"
echo "        ./golden-card/stamp-card.py 2"
echo "        ./golden-card/stamp-card.py 3     ... and so on"
echo
echo "NOTE: this robot's SSH host keys were just deleted, so your Mac will report"
echo "a changed host key for $THIS_HOST after its next boot. Clear it with:"
echo "  ssh-keygen -R $THIS_HOST.local"

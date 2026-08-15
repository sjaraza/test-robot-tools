#!/usr/bin/env bash
# Say this robot's name and IP address out loud.
#
# Run at boot by roboshine-announce.service. To hear it now:
#
#   bash ~/test-robot-tools/announce.sh
#
# Never fails the boot: if there's no speaker, no espeak-ng, or no network yet,
# it says so on stderr and exits 0. A robot that won't finish booting because it
# couldn't talk would be a poor trade.

set -uo pipefail

WAIT_SECONDS=60      # WiFi on a Zero 2 W can take a while to get an address
SPEED=150            # espeak-ng words per minute; 175 is its default, a bit fast

log() { echo "announce: $*"; }

if ! command -v espeak-ng >/dev/null && ! command -v espeak >/dev/null; then
  log "espeak-ng isn't installed; run setup-announce.sh" >&2
  exit 0
fi
SAY="$(command -v espeak-ng || command -v espeak)"

# --- wait for an address ---------------------------------------------------
address=""
for (( waited = 0; waited < WAIT_SECONDS; waited += 2 )); do
  # hostname -I lists every address; the first is the one we want.
  address="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [[ -n "$address" ]] && break
  sleep 2
done

host="$(hostname)"

# --- build something worth listening to -----------------------------------
# "robot-7" reads better as "robot 7", and espeak says each dotted octet as a
# number, so 192.168.1.5 comes out as "one hundred ninety two dot ...". Long,
# but unambiguous across a noisy room, which is the point.
spoken_host="${host//-/ }"

if [[ -n "$address" ]]; then
  spoken_address="${address//./ dot }"
  text="$spoken_host ready. Address $spoken_address"
else
  text="$spoken_host ready. No network address."
  log "no IP address after ${WAIT_SECONDS}s" >&2
fi

log "saying: $text"

# 2>&1 into the log: with no sound card configured espeak writes ALSA errors,
# and they belong in the journal rather than nowhere.
if ! "$SAY" -s "$SPEED" "$text" 2>&1; then
  log "couldn't play audio -- is the speaker set up? (~/robot-hat/i2samp.sh)" >&2
fi

exit 0

# test-robot-tools

Everything a student needs to talk to a robot, running **on the robot itself**.
Their laptop needs nothing installed — not Python, not a VM. Just `ssh`, which
macOS and Windows 10/11 already ship.

```
STUDENT LAPTOP                 ROBOT (Pi Zero 2 W)
Terminal + ssh   ─────────►    splash screen on login
(nothing installed)            cockpit  ->  menu + dashboard
                               update  ->  git pull
```

## What a student does

```bash
ssh robot@robot-1.local
```

They're greeted by the splash screen, then:

| Type | What it does |
|---|---|
| `cockpit` | Take the controls — dashboard and menu |
| `robostat` | Prints just the stats and exits |
| `update` | Pulls the latest code from GitHub (only needed now and then) |

## robostat — stats without the menu

```
╭──────────────────────────────────────────────────────────╮
│ ROBOT-1                                                  │
├──────────────────────────────────────────────────────────┤
│  batt 8.32V ██████ 96%        temp 42.9°C ███░░░         │
│   mem 202/415MB ███░░░        load 0.13                  │
│  disk 7.6/28.3GB ██░░░░       wifi -28dBm ██████         │
│    up 1h 43m                 power healthy               │
│  host robot-1.local  192.168.1.5                         │
╰──────────────────────────────────────────────────────────╯
```

```bash
robostat            # one snapshot
robostat --watch    # refresh every 2s, Ctrl-C to stop
```

`--watch` is the useful one while driving — you can see the battery sag under
motor load.

The alias is added by a one-time setup script:

```bash
bash ~/test-robot-tools/setup-aliases.sh
source ~/.bashrc
```

Safe to re-run — it rewrites its own managed block in `~/.bashrc` rather than
appending, so duplicates can't pile up, and it clears out the older `launch`
alias if a robot still has one. It backs up `~/.bashrc` first.

All the reading logic is imported from `robotmenu.py`, so `robostat` and the
cockpit can't drift apart.

## The menu

A live dashboard sits above the menu: battery voltage and percentage, CPU
temperature, memory, disk, WiFi signal strength, address, uptime, and
undervoltage/throttling warnings. `r` refreshes it.

```
╭──────────────────────────────────────────────────╮
│  ████   ███  ████   ███  █████         █         │
│  █   █ █   █ █   █ █   █   █          ██         │
│  ████  █   █ ████  █   █   █    ███    █         │
│  █  █  █   █ █   █ █   █   █           █         │
│  █   █  ███  ████   ███    █          ███        │
├──────────────────────────────────────────────────┤
│  battery   7.92 V  ████████░░  76%               │
│  cpu temp  48.3 °C  ██████░░░░                   │
│  memory    118 / 420 MB  ███░░░░░░░              │
│  wifi      -54 dBm  █████████░                   │
│  address   robot-1.local  (192.168.1.5)          │
│  uptime    1h 24m                                │
│  power     healthy                               │
├──────────────────────────────────────────────────┤
│   1  Measure distance                            │
│   2  Move the car                                │
│   3  Steer the wheels                            │
│   4  Pan / tilt the camera                       │
│   5  Read the line sensors                       │
│   6  Stop everything                             │
│   7  Diagnostics                                 │
│   r  Refresh                                     │
│   q  Quit                                        │
╰──────────────────────────────────────────────────╯
```

Motors are always stopped on the way out of an action, including on Ctrl-C.

## Camera stream

Menu item 7 toggles it. Once on, open the printed URL in any browser — nothing
to install on the laptop, no JavaScript in the page. The browser renders MJPEG
natively in an `<img>` tag.

```
http://robot-1.local:8080/
```

The dashboard shows a `cam` row: `off`, `on · idle`, or `live · 2 watching`.

### Why MJPEG rather than H.264 or WebRTC

MJPEG has no inter-frame prediction, so there's no encoder or decoder buffer to
fill — a frame displays as soon as it lands. H.264 would use 3–5× less bandwidth
but a browser can't play a raw H.264 stream from a URL: you'd need WebRTC
(signalling, SDP, ICE) or Media Source Extensions (JavaScript feeding a
`SourceBuffer`, plus fMP4 muxing on the robot). Neither is worth it here.

Latency work that's already in place:

- `rpicam-vid --flush`, so frames aren't held in the encoder
- `TCP_NODELAY`, so Nagle doesn't delay each small write
- one `write()` per frame, so a frame is one packet burst rather than four
- a small send buffer, so a network hiccup can't queue up stale frames
- only the newest frame is kept; a slow viewer skips ahead rather than catching
  up through old frames

### Bandwidth

The camera only encodes while a browser is watching, and releases itself after
five idle minutes — so leaving it on costs nothing when nobody's looking.

| Setting | Per robot | 20 robots |
|---|---|---|
| 320x240 @ 24fps | ~2–3 Mbps | won't work |
| 320x240 @ 10fps | ~0.6–1.2 Mbps | marginal |
| 320x240 @ 5fps | ~0.3 Mbps | fine |

Default is 24fps, which suits one or two robots. The menu asks, so a student can
drop it. These are estimates — MJPEG size depends on how detailed the scene is.

```bash
python3 camstream.py --fps 5 --port 8080     # run it directly
python3 camstream.py --quality 55            # smaller frames, if supported
```

`--quality` is opt-in because not every `rpicam-vid` build accepts it. The log at
`/tmp/robotcam.log` will say if it doesn't.

## Setting up a robot (instructor, once per card)

```bash
git clone https://github.com/sjaraza/test-robot-tools.git ~/test-robot-tools
bash ~/test-robot-tools/install.sh
bash ~/test-robot-tools/setup-aliases.sh
source ~/.bashrc
```

`install.sh` writes the splash into `/etc/motd` — generated from the robot's own
hostname, so `robot-7` shows `ROBOT-7` with no per-card editing.
`setup-aliases.sh` installs `cockpit`, `robostat` and `update`.

`update.sh` re-runs `install.sh` after every pull, so a changed splash or menu
takes effect right away.

The PiCar-X and robot-hat libraries live in `~/picar-x` and `~/robot-hat` on
these robots; `install.sh` makes sure they're writable and the menu adds them to
the Python path if they aren't already importable.

## Direct use

```bash
python3 robotmenu.py            # dashboard and menu
python3 robotmenu.py --splash   # print the banner (what install.sh pipes to motd)
python3 robotmenu.py --probe    # what hardware can we reach, and what failed
```

`--probe` is the first thing to run when something looks wrong: it reports
whether `picarx` and `robot_hat` import, the battery reading, whether `vcgencmd`
and `rpicam-vid` exist, and the actual method names on the `Picarx` class.

## Notes

- Standard library only. No pip installs on the robot beyond the PiCar-X
  software that's already there.
- The block-letter font covers `ROBOT` and digits. Any other hostname falls back
  to plain text rather than a half-rendered banner.
- Robots are addressed by mDNS name (`robot-3.local`), never by IP.
- Camera streaming is deliberately **not** here yet — see the
  `camera-streaming-wip` branch for the parked work and why.

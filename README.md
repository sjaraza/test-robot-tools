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

## Quick start — setting up your robot

Do this once, on your own robot, after you've imaged its card. Three commands.

**1. Log in.** Replace `1` with your robot's number:

```bash
ssh robot@robot-1.local
```

**2. Run the setup.** Copy this whole line:

```bash
curl -fsSL https://raw.githubusercontent.com/sjaraza/test-robot-tools/main/setup-all.sh | bash
```

It installs the PiCar-X software and the robot tools. **This takes 30–60 minutes**
— leave it running and don't close the window. It prints what it's doing as it
goes, and keeps a log at `~/picarx-install.log`.

**3. Reboot, and log back in:**

```bash
sudo reboot
```

Wait a minute, then `ssh robot@robot-1.local` again. You should see a big
`ROBOT-1` splash screen. Now you can type:

| Command | What it does |
|---|---|
| `cockpit` | Drive the robot, read its sensors, start the camera |
| `robostat` | Battery, temperature, WiFi signal |
| `update` | Get the latest version of these tools |
| `sb` | Re-read `~/.bashrc` after editing it |
| `eb` | Edit `~/.bashrc` in `vi` |

If something looks wrong, run `python3 ~/test-robot-tools/robotmenu.py --probe`
and show the output to your instructor.

## What a student does day to day

```bash
ssh robot@robot-1.local
cockpit
```

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
│  batt 8.32V ██████ 96%     temp 42.9°C ███░░░    │
│   mem 202/415MB ███░░░     load 0.13             │
│  disk 7.6/28.3GB ██░░░░    wifi -28dBm ██████    │
│    up 1h 43m              power healthy          │
│   cam live · 1 watching    host robot-1.local    │
├──────────────────────────────────────────────────┤
│   1  Drive with the arrow keys                   │
│   2  Measure distance                            │
│   3  Drive for a set time                        │
│   4  Steer to an angle                           │
│   5  Point the camera (arrow keys)               │
│   6  Read the line sensors                       │
│   7  Camera stream on / off                      │
│   8  Camera logs                                 │
│   9  Stop everything                             │
│  10  Diagnostics                                 │
│   r  Refresh    q  Quit                          │
╰──────────────────────────────────────────────────╯
```

Motors are always stopped on the way out of an action, including on Ctrl-C.

Arrow-key driving and pan/tilt both ask for a step size first, and driving has a
0.45s dead-man stop: a terminal has no key-release event, so the motors cut when
key auto-repeat stops. Without that, letting go over a laggy SSH link would leave
the car driving into a wall.

Live views (distance, line sensors) update one line in place and stop on **any**
keypress — Ctrl-C isn't obvious to a 15-year-old.

Distance readings are the median of 3 pings spaced 60ms apart. An HC-SR04 needs
roughly that long to settle; polling flat out measured 408 reads/s and returned
wildly wrong numbers, because echoes from earlier pings landed inside the next
measurement window. The line shows the spread (`±`) so you can see when the
sensor disagrees with itself.

## Camera stream

Menu item 7 toggles it. Once on, open the printed URL in any browser — nothing
to install on the laptop, no JavaScript in the page. The browser renders MJPEG
natively in an `<img>` tag.

```
http://robot-1.local:8080/
```

The dashboard shows a `cam` row: `off`, `on · idle`, or `live · 2 watching`.
Menu item 8 shows the stream's log (`/tmp/robotcam.log`) and live viewer count —
the first place to look when the picture won't appear.

Item 7 also offers a **test pattern** instead of the camera: colour bars, a
sweeping bar and a frame counter, generated in Python with no camera involved. If
that appears in the browser, the network, HTTP path and browser are all fine and
the camera is at fault. If it doesn't, the camera is innocent. It runs at a fixed
5fps because it's drawn pixel by pixel.

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

## Manual setup, step by step

What `setup-all.sh` does for you, if you'd rather run the pieces yourself.

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
- Arrow keys are decoded in both encodings, CSI (`ESC [ A`) and SS3 (`ESC O A`),
  since PuTTY, tmux and some Windows terminals send the latter.

## Installing the PiCar-X software on a fresh robot

`setup-picarx.sh` does the whole SunFounder install in one run — `apt` packages,
robot-hat, vilib, picar-x, and the calibration directory.

```bash
git clone https://github.com/sjaraza/test-robot-tools.git ~/test-robot-tools
bash ~/test-robot-tools/setup-picarx.sh
```

Run it **as the normal user**, not with `sudo` — it calls `sudo` itself where
needed. Expect 30–60 minutes on a Pi Zero 2 W; vilib pulls in OpenCV and that's
the longest single step. Everything is logged to `~/picarx-install.log`.

```bash
bash setup-picarx.sh --skip-upgrade    # skip apt upgrade, much faster
bash setup-picarx.sh --with-sound      # also run robot-hat's i2samp.sh
bash setup-picarx.sh --yes             # no confirmation prompt
```

Safe to re-run: existing checkouts are updated rather than re-cloned.

Before it starts it checks sudo works, GitHub is reachable, there's enough disk
space, and the clock is sane — a Zero 2 W has no battery-backed clock, and a
wrong date makes `apt` reject repository metadata in a way that's annoying to
diagnose.

It also creates `/opt/picar-x` and makes it yours. picarx writes its servo
calibration to that hardcoded path, and on a fresh system it doesn't exist while
`/opt` is root-owned, so `Picarx()` otherwise fails with
`PermissionError: [Errno 13]` — errno 13 on a path that doesn't exist, because
the refusal comes from the parent directory.

Sound is opt-in because `i2samp.sh` is interactive and offers to reboot. When it
asks about rebooting, answer **N** and reboot yourself afterwards.

Afterwards:

```bash
sudo reboot
python3 ~/test-robot-tools/robotmenu.py --probe
```

## Computer vision, and the laptop side

Laptop and VM code lives in a separate repo:
**[test-robot-lab](https://github.com/sjaraza/test-robot-lab)**. It has
`cvclient.py` (pulls this stream, hands you numpy frames, ships Haar-cascade and
motion examples) and `setup-vm.sh` (one-time Ubuntu 24.04 setup: VS Code, OpenCV
with contrib, mosh, mDNS).

CV runs there rather than here on purpose: a Zero 2 W has four slow cores and
512MB, so the robot captures and hardware-encodes while the laptop does the
thinking. The cockpit prints the exact command when you start the stream.

## mosh

```bash
bash ~/test-robot-tools/setup-mosh.sh
```

Then connect with `mosh robot@robot-1.local` instead of `ssh`. On a congested
2.4GHz AP it's a large improvement: keystrokes echo locally rather than waiting
for a round trip, and sessions survive dropouts, roaming and a closed lid — which
matters for the cockpit's full-screen redraws.

Needs installing on both ends. `setup-picarx.sh` now includes it for new robots,
so `setup-mosh.sh` is for robots already set up.

⚠️ mosh requires a UTF-8 locale and refuses to start without one. This robot has
had exactly that problem before, so the script checks and prints the fix.

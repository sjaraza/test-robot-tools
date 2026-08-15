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
| `robotreboot` | Reboot the robot |
| `robotoff` | Shut it down properly — do this before unplugging |

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

### `update` is the only command to remember

```bash
update
```

It runs `setup-all.sh`, which works out what's already there and does only the
rest. Same command for a fresh robot and for picking up changes later.

```
== 2. PiCar-X software ==
   ok   robot-hat
   --   vilib is missing
   ok   picar-x

  Installing: vilib
  This can take 30-60 minutes. Leave the window open.
```

On a robot that's fully set up it finishes in seconds and installs nothing:

```
   ok   robot-hat
   ok   vilib
   ok   picar-x
   ok   nothing to install
...
Done -- everything was already installed, just updated.
```

Built to be run often:

- **No sudo unless something changed.** `/etc/motd` is only written when the
  splash actually differs, so a routine `update` never asks for a password.
- **No clutter.** `~/.bashrc` is only rewritten when the aliases differ, and
  there's a single `~/.bashrc.robotbak`, not one backup per run.
- **New aliases arrive automatically**, so a student who only types `update`
  still ends up with them as the tools grow.
- **Each library is checked separately**, so a missing `vilib` doesn't rebuild
  robot-hat or repeat the `apt upgrade`.
- **Never re-installs what's present.** To take upstream SunFounder changes
  deliberately, run `setup-picarx.sh --force`.

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
- The block-letter font covers A–Z, 0–9 and `-`, so `robot-A` and `robot-12` both
  render. A hostname with anything else falls back to plain text rather than a
  half-rendered banner.
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

Safe to re-run, and cheap to re-run: each library is skipped if it already
imports, so a failure part-way through doesn't redo the parts that succeeded.
That matters because vilib is the OpenCV step — a failure there used to mean
rebuilding robot-hat and repeating the `apt upgrade` on the next attempt.
Checkouts are still `git pull`ed rather than re-cloned, so the examples and
`i2samp.sh` stay current. Use `--force` to reinstall regardless.

`setup-all.sh` skips the whole step if `picarx`, `robot_hat` and `vilib` all
import.

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

## roboshine — write your own robot scripts

A small Python library on the robot, importable from any directory:

```python
import roboshine as robot

robot.steerLeft(20)          # point the wheels
robot.driveForward(20)       # start moving, curving left
robot.wait(2)                # ...for two seconds
robot.stop()

# Nothing blocks except wait(), so you can watch a sensor while driving:
robot.steerStraight()
robot.driveForward(15)
while robot.get_distance_cm() > 25:
    robot.wait(0.1)
robot.stop()
```

| Command | What it does |
|---|---|
| `driveForward(speed=10)` | start driving forward; keeps going until `stop()` |
| `driveBack(speed=10)` | start driving backward; keeps going until `stop()` |
| `stop()` | stop the motors; wheels stay pointed where they were |
| `steerLeft(degrees=30)` | point the wheels left, 0–30. Doesn't drive |
| `steerRight(degrees=30)` | point the wheels right, 0–30. Doesn't drive |
| `steerStraight()` | point them straight ahead |
| `lookLeft(degrees=90)` / `lookRight(...)` | turn the camera, 0–90 |
| `lookUp(degrees=65)` / `lookDown(degrees=35)` | tilt the camera |
| `lookStraight()` | camera straight ahead and level |
| `get_distance_cm()` | centimetres to the thing in front, or −1 if nothing is in range |
| `wait(seconds)` | pause the script while the robot carries on |
| `showHelp()` | print all of the above |

```bash
python3 -c "import roboshine; roboshine.showHelp()"
python3 ~/test-robot-tools/examples/my_first_drive.py
```

**Steering and driving are separate commands.** A curve is two steps: point the
wheels, then drive. `driveForward()` deliberately leaves the steering alone — if
it straightened the wheels, `steerLeft()` would be silently undone. This chassis
steers like a car, so it can't spin on the spot.

**The camera's two axes are separate too**, so `lookLeft(40)` then `lookUp(20)`
leaves it pointing up *and* left. `lookStraight()` resets both. Tilt is
asymmetric because the mount is: 65° up, 35° down.

**Nothing blocks except `wait()`.** `driveForward()` sets the motors going and
returns immediately, so the robot keeps driving until `stop()` — which is what
lets a script watch a sensor while moving. Keeping the pauses in one obvious
command is easier to reason about than commands that sometimes take time.

Three more deliberate choices:

- **The motors stop when your script ends**, however it ends — normally, on a
  crash, or on Ctrl-C. A script exiting with the robot still driving is how
  robots end up under the furniture.
- **The hardware opens on first use, not on import.** So `showHelp()` works with
  no robot attached, and a loose servo cable can't make `import roboshine` fail.
- **Arguments are checked before anything moves.** A typo tells you it's a typo
  rather than complaining about a library, and a bad `seconds` is caught before
  the wheels turn.

`install.sh` makes it importable by writing a `.pth` file into your
site-packages that points at this repo — so `update` keeps the library current
with no reinstall step.

## Computer vision, and the laptop side

Laptop and VM code lives in a separate repo:
**[test-robot-lab](https://github.com/sjaraza/test-robot-lab)**. It has
`cvclient.py` (pulls this stream, hands you numpy frames, ships Haar-cascade and
motion examples) and `setup-vm.sh` (one-time Ubuntu 24.04 setup: VS Code, OpenCV
with contrib, mosh, mDNS).

CV runs there rather than here on purpose: a Zero 2 W has four slow cores and
512MB, so the robot captures and hardware-encodes while the laptop does the
thinking. The cockpit prints the exact command when you start the stream.

### Always use `robotoff` before unplugging

Pulling the power while Linux is still writing is the main way SD cards die, and
a corrupt card means re-imaging. `robotoff` shuts down cleanly; wait for the green
LED to stop flickering before you disconnect.

## Announcing itself on boot

```bash
bash ~/test-robot-tools/setup-announce.sh
```

The robot then says its name and IP address out loud every time it boots —
*"robot 7 ready. Address 192 dot 168 dot 1 dot 5"*. Genuinely useful when twenty
identical robots are on a table and you need to know which one just came back.

Light enough not to worry about: `espeak-ng` is about a megabyte and speaks in
well under a second on a Zero 2 W. It needs the speaker working, so run
`~/robot-hat/i2samp.sh` first (or `setup-picarx.sh --with-sound`).

```bash
bash ~/test-robot-tools/announce.sh                    # hear it now
journalctl -u roboshine-announce -b                    # what it did at boot
bash ~/test-robot-tools/setup-announce.sh --remove     # turn it off
```

It can't break a boot: with no speaker, no espeak-ng, or no network yet, it says
so in the journal and exits cleanly. It waits up to 60s for an IP, because
"network is online" and "WiFi has an address" aren't the same thing on a Pi.

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

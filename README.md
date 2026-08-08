# test-robot-tools

Everything a student needs to talk to a robot, running **on the robot itself**.
Their laptop needs nothing installed — not Python, not a VM. Just `ssh`, which
macOS and Windows 10/11 already ship.

```
STUDENT LAPTOP                 ROBOT (Pi Zero 2 W)
Terminal + ssh   ─────────►    splash screen on login
(nothing installed)            launch  ->  menu + dashboard
                               update  ->  git pull
```

## What a student does

```bash
ssh robot@robot-1.local
```

They're greeted by the splash screen, then:

| Type | What it does |
|---|---|
| `launch` | Opens the dashboard and menu |
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
bash ~/test-robot-tools/setup-robostat.sh
source ~/.bashrc
```

Safe to re-run; it won't duplicate the alias. All the reading logic is imported
from `robotmenu.py`, so `robostat` and the menu can't drift apart.

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

## Setting up a robot (instructor, once per card)

```bash
git clone https://github.com/sjaraza/test-robot-tools.git ~/test-robot-tools
bash ~/test-robot-tools/install.sh
```

`install.sh` writes the splash into `/etc/motd` — generated from the robot's own
hostname, so `robot-7` shows `ROBOT-7` with no per-card editing. Then add the two
aliases it prints to `~/.bashrc`:

```bash
alias launch='python3 ~/test-robot-tools/robotmenu.py'
alias update='bash ~/test-robot-tools/update.sh'
```

`update.sh` re-runs `install.sh` after every pull, so a changed splash or menu
takes effect right away.

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

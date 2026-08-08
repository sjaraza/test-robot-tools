# test-robot-tools

Tools for driving the test robot (Raspberry Pi Zero 2 W, Raspberry Pi OS trixie,
arm64) from a laptop.

**Design rule: the robot stays thin.** It has 512 MB of RAM and shares one
2.4 GHz radio with every other robot. Anything that can happen on the laptop
happens on the laptop.

## robotcam.py — camera feed, processed on your laptop

Runs **on your laptop**. Nothing is installed on the robot.

```
ROBOT                                    YOUR LAPTOP
─────                                    ───────────
rpicam-vid                               robotcam.py
  ├─ camera capture                        ├─ ffmpeg decodes H.264
  ├─ hardware H.264 encode                 ├─ frames -> numpy arrays
  └─ writes to stdout  ──── ssh ────►      ├─ process_frame(frame)  <- you edit
                                           └─ optional preview window
```

The robot's only job is capture and encode, both done in hardware. It runs no
Python, opens no ports, and needs no setup — `rpicam-vid` ships with Raspberry
Pi OS.

Just run it. It asks which robot and who you are, then ssh asks for the
password. Nothing to edit first, so the same file works for every student.

```bash
./robotcam.py
```
```
Which robot? (just the number, e.g. 3): 3
Username [robot]: robot
robot@robot-3.local's password:
robot   : robot@robot-3.local
stream  : 320x240 @ 10fps, 230 kbps, hardware H.264
ctrl-c to stop
```

**No credentials are stored anywhere** — not in this file, not in a config, not
in an environment variable. The password prompt comes from `ssh` itself and you
answer it on every launch. That's deliberate: the script is meant to be handed
out as-is.

Pass values in to skip the questions, plus flags for anything else:

```bash
./robotcam.py 3 --user robot             # no prompts
./robotcam.py 3 --width 640 --height 480 --fps 15
./robotcam.py 3 --vflip                  # camera mounted upside down
./robotcam.py 3 --no-window              # headless processing
./robotcam.py 3 --check                  # diagnose that robot's camera
./robotcam.py 3 --use-key                # use your ssh key instead of a password
```

Press `q` or Esc in the window to quit, or Ctrl-C.

### What students edit

Just `process_frame(frame, state)` near the top of `robotcam.py`. It receives a
BGR numpy array and returns the image to display. There's a commented-out
red-object tracker in there as a worked example.

### Laptop requirements

Three packages, installed **once into the VM image** — students install nothing:

```bash
sudo apt install -y ffmpeg python3-opencv python3-numpy
```

No `sshpass`, no key setup, no stored credentials — `ssh` and `ffmpeg` do the
work.

The script verifies ffmpeg actually *runs* rather than just existing on PATH. A
present-but-broken ffmpeg (e.g. Homebrew where `x265` was upgraded and ffmpeg
wasn't relinked) otherwise shows up as a stream that silently produces no
frames. If you see that message, `brew reinstall ffmpeg` or
`sudo apt install --reinstall ffmpeg`.

If a robot's SD card gets reimaged its SSH identity changes, and ssh will refuse
to connect until you clear the old one. The script detects this and prints the
fix:

```bash
ssh-keygen -R robot-3.local
```

## Bandwidth: read this before class

Video is the heaviest thing on the network by a wide margin.

| Resolution | fps | Per robot | 20 robots |
|---|---|---|---|
| 320x240 | 10 | ~230 kbps | ~4.6 Mbps |
| 640x480 | 15 | ~1.4 Mbps | ~28 Mbps |

A single 2.4 GHz radio will not carry 20 simultaneous 640x480 streams. The
defaults are deliberately 320x240 @ 10fps. Treat 640x480 as a one-robot-at-a-time
demo setting.

## Notes

- Camera confirmed on the fleet: **ov5647** (Pi Camera Module v1, 5MP). Its
  native modes are 640x480, 1296x972, 1920x1080 and 2592x1944 — so 640x480 is a
  direct sensor read, while 320x240 is that same read downscaled by the ISP.
  Going below 640x480 saves network bandwidth, not work on the robot.
- The fleet is uniform: user `robot` on hosts `robot-1` ... `robot-N`. Pass just
  the number; the script builds `robot@robot-N.local` for you.
- Always address robots by **mDNS name** (`robot-3.local`), never by IP.
- Raspberry Pi OS trixie uses **libcamera** (`rpicam-vid`, `rpicam-hello`). The
  old `raspivid` / `raspistill` stack is gone — ignore tutorials mentioning them.
- If you run this inside a VirtualBox VM, the VM needs a **bridged** network
  adapter. With NAT, `.local` mDNS resolution generally fails.

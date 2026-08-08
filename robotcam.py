#!/usr/bin/env python3
"""Watch the robot's camera in your browser. Nothing to install, anywhere.

    ROBOT                          YOUR LAPTOP                     BROWSER
    -----                          -----------                     -------
    rpicam-vid                     robotcam.py                     localhost:8000
      camera capture                 reads JPEGs over ssh   ---->    <img>
      hardware MJPEG encode          re-serves them locally
      writes to stdout  --- ssh -->

The robot runs one process and has nothing installed on it -- `rpicam-vid` ships
with Raspberry Pi OS. Your laptop needs only Python 3, which it already has: no
ffmpeg, no OpenCV, no pip packages. The browser does the decoding.

Usage:

    ./robotcam.py                    # asks robot number, username, password
    ./robotcam.py 3 --user robot     # skip the questions
    ./robotcam.py 3 --width 640 --height 480 --fps 15
    ./robotcam.py 3 --check          # diagnose that robot's camera
    ./robotcam.py 3 --no-browser     # don't auto-open a browser
"""

import argparse
import http.server
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser

# No password lives in this file. ssh asks you for it directly, every launch.
DEFAULT_USER = "robot"

SOI = b"\xff\xd8"   # JPEG start-of-image
EOI = b"\xff\xd9"   # JPEG end-of-image

PAGE = """<!DOCTYPE html>
<html>
<head><title>{title}</title><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;background:#111;color:#999;font-family:system-ui,sans-serif">
  <img src="/stream.mjpg" style="display:block;margin:0 auto;width:100%;max-width:{width}px">
  <p style="text-align:center;font-size:13px">{title} &mdash; {width}x{height} @ {fps}fps</p>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# talking to the robot
# ---------------------------------------------------------------------------

def ssh_options(use_key=False):
    """Shared ssh flags.

    By default we force password authentication so every student gets the same
    experience -- asked for the password on every launch -- regardless of
    whether a key happens to be installed on their laptop.

    accept-new trusts a robot you've never met, but a robot whose identity
    *changed* still stops you. That happens for real whenever an SD card is
    reimaged; see handle_host_key_error().
    """
    options = [
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=accept-new",
    ]
    if not use_key:
        options += [
            "-o", "PubkeyAuthentication=no",
            "-o", "PreferredAuthentications=password",
            "-o", "NumberOfPasswordPrompts=1",
        ]
    return options


def remote_command(args):
    """The rpicam-vid invocation that runs on the robot.

    MJPEG rather than H.264: every frame is a standalone JPEG, so a browser can
    display the stream directly in an <img> tag and no decoder is needed on the
    laptop. Costs more bandwidth than H.264 -- see the table in the README.
    """
    return (
        "rpicam-vid "
        "--timeout 0 "               # run until we disconnect
        "--nopreview "               # headless robot, no display to draw on
        f"--width {args.width} --height {args.height} "
        f"--framerate {args.fps} "
        "--codec mjpeg "
        "--flush "                   # don't sit on buffered output
        f"{'--hflip ' if args.hflip else ''}"
        f"{'--vflip ' if args.vflip else ''}"
        "--output -"                 # ...to stdout, which becomes our pipe
    )


def host_of(target):
    return target.split("@", 1)[-1]


def handle_host_key_error(target, stderr):
    """A reimaged robot has a new host key. Tell them exactly how to clear it."""
    if "REMOTE HOST IDENTIFICATION HAS CHANGED" not in (stderr or ""):
        return False
    host = host_of(target)
    print(
        f"\n{host} has a different SSH identity than last time.\n"
        "That is normal if its SD card was reimaged. Clear the old key and retry:\n\n"
        f"    ssh-keygen -R {host}\n",
        file=sys.stderr,
    )
    return True


def check_robot(target, use_key=False):
    """Report what the robot thinks about its camera."""
    print(f"checking {target} ...\n")
    probe = (
        "echo '--- os ---'; grep PRETTY_NAME /etc/os-release; "
        "echo '--- rpicam-vid ---'; command -v rpicam-vid || echo MISSING; "
        "echo '--- cameras ---'; rpicam-hello --list-cameras 2>&1 | head -20"
    )
    result = subprocess.run(
        ["ssh", *ssh_options(use_key), target, probe],
        capture_output=True, text=True,
    )
    print(result.stdout or "(no output)")
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0 and not handle_host_key_error(target, result.stderr):
        print(f"\ncould not reach {target} -- check the robot is powered on and\n"
              "joined to the same WiFi, then try again.", file=sys.stderr)
    return result.returncode


# ---------------------------------------------------------------------------
# pulling JPEG frames out of the ssh pipe
# ---------------------------------------------------------------------------

class FrameBroker:
    """Holds the newest JPEG frame and wakes up waiting browser connections."""

    def __init__(self):
        self.frame = None
        self.count = 0
        self.condition = threading.Condition()
        self.finished = False

    def publish(self, jpeg):
        with self.condition:
            self.frame = jpeg
            self.count += 1
            self.condition.notify_all()

    def close(self):
        with self.condition:
            self.finished = True
            self.condition.notify_all()

    def next_frame(self, timeout=5.0):
        with self.condition:
            if self.finished:
                return None
            if not self.condition.wait(timeout):
                return None
            return self.frame


def split_jpegs(stream, broker, stop):
    """Read the MJPEG byte stream and hand each complete JPEG to the broker.

    Frames are found by scanning for the JPEG start/end markers. That is safe
    for MJPEG because 0xFF bytes inside compressed data are byte-stuffed as
    0xFF00, so a bare 0xFFD9 only ever means end-of-image.
    """
    buf = bytearray()
    while not stop.is_set():
        chunk = stream.read1(65536)
        if not chunk:
            break
        buf += chunk

        while True:
            start = buf.find(SOI)
            if start < 0:
                # Keep a trailing byte: it might be the first half of a marker.
                del buf[:-1]
                break
            end = buf.find(EOI, start + 2)
            if end < 0:
                del buf[:start]      # drop anything before the partial frame
                break
            broker.publish(bytes(buf[start:end + 2]))
            del buf[:end + 2]

    broker.close()


# ---------------------------------------------------------------------------
# serving it to the browser
# ---------------------------------------------------------------------------

class StreamingHandler(http.server.BaseHTTPRequestHandler):
    broker = None
    args = None
    title = ""

    def log_message(self, fmt, *a):
        pass  # a line per request is just noise here

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = PAGE.format(title=self.title, width=self.args.width,
                               height=self.args.height, fps=self.args.fps).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Content-Type",
                             "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while True:
                    frame = self.broker.next_frame()
                    if frame is None:
                        if self.broker.finished:
                            break
                        continue
                    self.wfile.write(b"--FRAME\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass  # viewer closed the tab
        else:
            self.send_error(404)


class StreamingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


# ---------------------------------------------------------------------------
# prompts
# ---------------------------------------------------------------------------

def prompt_for_robot():
    """Ask which robot to connect to. Accepts '3' or 'robot-3'."""
    while True:
        try:
            value = input("Which robot? (just the number, e.g. 3): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit("cancelled")

        value = value.removeprefix("robot-").removesuffix(".local")
        if value.isdigit() and int(value) > 0:
            return value
        if value:
            print(f"  '{value}' doesn't look like a robot number -- try 1, 2, 3 ...")


def prompt_for_user():
    """Ask which login name to use, defaulting to the fleet's usual one."""
    try:
        value = input(f"Username [{DEFAULT_USER}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit("cancelled")
    return value or DEFAULT_USER


def resolve_target(value, user):
    """Turn a robot number and login name into a full ssh target.

    Hosts are `robot-1` ... `robot-N`, always addressed by mDNS name, never IP.

        3, robot          -> robot@robot-3.local
        robot-3, student  -> student@robot-3.local
    """
    if "@" in value:
        return value
    host = f"robot-{value}" if value.isdigit() else value
    if not host.endswith(".local"):
        host += ".local"
    return f"{user}@{host}"


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("robot", nargs="?",
                        help="robot number, e.g. 3 for robot-3.local; "
                             "you'll be asked if you leave it out")
    parser.add_argument("--user", help="login name; you'll be asked if omitted")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--hflip", action="store_true")
    parser.add_argument("--vflip", action="store_true")
    parser.add_argument("--no-browser", action="store_true",
                        help="print the URL instead of opening a browser")
    parser.add_argument("--check", action="store_true",
                        help="probe the robot's camera setup and exit")
    parser.add_argument("--use-key", action="store_true",
                        help="allow SSH key auth instead of asking for a password")
    parser.add_argument("--debug", action="store_true",
                        help="show the ssh command and ssh's own output")
    args = parser.parse_args()

    robot = args.robot or prompt_for_robot()
    user = args.user or prompt_for_user()
    target = resolve_target(robot, user)

    if args.check:
        sys.exit(check_robot(target, use_key=args.use_key))

    ssh_cmd = ["ssh", *ssh_options(args.use_key), target, remote_command(args)]
    if args.debug:
        print("ssh:", " ".join(ssh_cmd), file=sys.stderr)

    ssh_err = None if args.debug else tempfile.TemporaryFile()
    ssh = subprocess.Popen(ssh_cmd, stdout=subprocess.PIPE, stderr=ssh_err)

    broker = FrameBroker()
    stop = threading.Event()
    reader = threading.Thread(target=split_jpegs, args=(ssh.stdout, broker, stop),
                             daemon=True)
    reader.start()

    StreamingHandler.broker = broker
    StreamingHandler.args = args
    StreamingHandler.title = host_of(target)

    try:
        httpd = StreamingServer(("127.0.0.1", args.port), StreamingHandler)
    except OSError as exc:
        stop.set()
        ssh.terminate()
        sys.exit(f"could not listen on port {args.port} ({exc}). "
                 f"Try --port {args.port + 1}")

    url = f"http://localhost:{args.port}/"
    print(f"robot   : {target}")
    print(f"stream  : {args.width}x{args.height} @ {args.fps}fps, MJPEG")
    print(f"watch   : {url}")
    print("ctrl-c to stop\n")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    try:
        while True:
            httpd.handle_request() if False else time.sleep(0.25)
            if broker.finished:
                break
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        httpd.shutdown()
        httpd.server_close()
        if ssh.poll() is None:
            ssh.terminate()
        try:
            ssh.wait(timeout=5)
        except subprocess.TimeoutExpired:
            ssh.kill()

    if broker.count:
        print(f"\nstopped after {broker.count} frames")
        return

    print("\nNo video arrived.", file=sys.stderr)
    if ssh_err is not None:
        ssh_err.seek(0)
        text = ssh_err.read().decode(errors="replace").strip()
        if text:
            print("\n--- ssh / robot said ---", file=sys.stderr)
            print(text, file=sys.stderr)
            handle_host_key_error(target, text)
        else:
            print("ssh reported nothing. Re-run with --debug, or check that\n"
                  f"    ssh {target} true\n"
                  "works on its own.", file=sys.stderr)
    print(f"\nssh exit={ssh.returncode}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()

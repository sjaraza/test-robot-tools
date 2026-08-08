#!/usr/bin/env python3
"""Serve the robot's camera to a browser as MJPEG. Runs on the robot.

Normally you don't run this by hand -- the cockpit menu starts and stops it.
Directly:

    camstream.py                  serve on port 8080
    camstream.py --fps 5          gentler on the WiFi
    camstream.py --quality 55     smaller frames, if your rpicam-vid supports it

Design notes:

* MJPEG, because a browser renders it in a plain <img> tag with no JavaScript
  and nothing installed on the laptop.
* rpicam-vid does the encoding in hardware, so this process only ever copies
  already-compressed bytes. It never touches pixels.
* The encoder is started when the first browser connects and stopped when the
  last one leaves, so leaving the stream "on" costs nothing while nobody is
  watching. That matters with twenty robots sharing one 2.4GHz radio.
"""

import argparse
import http.server
import json
import os
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time

PID_FILE = "/tmp/robotcam.pid"
STATUS_FILE = "/tmp/robotcam.status"

SOI = b"\xff\xd8"   # JPEG start of image
EOI = b"\xff\xd9"   # JPEG end of image

PAGE = """<!DOCTYPE html>
<html>
<head>
  <title>{host}</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    body {{ margin:0; background:#111; color:#8b8b8b;
            font-family:system-ui,sans-serif; text-align:center }}
    img  {{ display:block; margin:0 auto; width:100%; max-width:{scale}px;
            image-rendering:pixelated }}
    p    {{ font-size:13px }}
  </style>
</head>
<body>
  <img src="/stream.mjpg" alt="camera">
  <p>{host} &mdash; {width}x{height} @ {fps}fps</p>
</body>
</html>
"""


class Broker:
    """Holds the newest JPEG frame and wakes waiting browser connections.

    Only ever one frame is kept. A queue would let a slow viewer fall behind and
    then play catch-up through stale frames, which is exactly the "video is
    seconds late" failure. Dropping frames is the correct behaviour here.
    """

    def __init__(self):
        self.frame = None
        self.sequence = 0
        self.condition = threading.Condition()

    def publish(self, jpeg):
        with self.condition:
            self.frame = jpeg
            self.sequence += 1
            self.condition.notify_all()

    def wake_all(self):
        with self.condition:
            self.condition.notify_all()

    def newest(self, after=0, timeout=5.0):
        """Wait for a frame newer than `after`. Returns (frame, sequence)."""
        with self.condition:
            if self.sequence <= after:
                if not self.condition.wait(timeout):
                    return None, after
            if self.sequence <= after:
                return None, after
            return self.frame, self.sequence


class Encoder:
    """rpicam-vid, started on demand and stopped when nobody is watching."""

    def __init__(self, args, broker):
        self.args = args
        self.broker = broker
        self.lock = threading.Lock()
        self.process = None
        self.reader = None

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def command(self):
        parts = [
            "rpicam-vid",
            "--timeout", "0",
            "--nopreview",
            "--width", str(self.args.width),
            "--height", str(self.args.height),
            "--framerate", str(self.args.fps),
            "--codec", "mjpeg",
            "--flush",
        ]
        # --quality isn't accepted by every rpicam-vid build, so it's opt-in.
        if self.args.quality:
            parts += ["--quality", str(self.args.quality)]
        if self.args.hflip:
            parts.append("--hflip")
        if self.args.vflip:
            parts.append("--vflip")
        parts += ["--output", "-"]
        return parts

    def start(self):
        with self.lock:
            if self.running:
                return
            log(f"starting encoder: {' '.join(self.command())}")
            self.process = subprocess.Popen(
                self.command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            self.reader = threading.Thread(target=self._pump, daemon=True)
            self.reader.start()

    def stop(self):
        with self.lock:
            if self.process is None:
                return
            log("stopping encoder (nobody watching)")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
        self.broker.wake_all()

    def _pump(self):
        """Split the MJPEG byte stream into frames.

        Scanning for the JPEG markers is safe here: 0xFF bytes inside compressed
        data are stuffed as 0xFF00, so a bare 0xFFD9 only ever means end-of-image.
        """
        process = self.process
        buffer = bytearray()
        while process is not None and process.poll() is None:
            chunk = process.stdout.read1(65536)
            if not chunk:
                break
            buffer += chunk
            while True:
                start = buffer.find(SOI)
                if start < 0:
                    del buffer[:-1]
                    break
                end = buffer.find(EOI, start + 2)
                if end < 0:
                    del buffer[:start]
                    break
                self.broker.publish(bytes(buffer[start:end + 2]))
                del buffer[:end + 2]

        if process is not None and process.poll() not in (None, 0, -15):
            errors = (process.stderr.read() or b"").decode(errors="replace")
            log(f"encoder exited {process.poll()}: {errors.strip()}")
        self.broker.wake_all()


class Viewers:
    """Counts connected browsers so the encoder knows when to run."""

    def __init__(self):
        self.lock = threading.Lock()
        self.count = 0
        self.last_seen = time.monotonic()

    def join(self):
        with self.lock:
            self.count += 1
            self.last_seen = time.monotonic()
            return self.count

    def leave(self):
        with self.lock:
            self.count = max(0, self.count - 1)
            self.last_seen = time.monotonic()
            return self.count

    def snapshot(self):
        with self.lock:
            return self.count, time.monotonic() - self.last_seen


def log(message):
    print(f"{time.strftime('%H:%M:%S')} {message}", flush=True)


def write_status(args, encoder, viewers):
    count, idle = viewers.snapshot()
    payload = {
        "port": args.port,
        "width": args.width,
        "height": args.height,
        "fps": args.fps,
        "viewers": count,
        "encoding": encoder.running,
        "idle_seconds": round(idle, 1),
        "url": f"http://{socket.gethostname().split('.')[0]}.local:{args.port}/",
    }
    try:
        with open(STATUS_FILE, "w") as handle:
            json.dump(payload, handle)
    except OSError:
        pass


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    # TCP_NODELAY. Without it Nagle holds small writes back waiting for more
    # data, which on a frame-at-a-time stream is pure added latency.
    disable_nagle_algorithm = True
    args = None
    broker = None
    encoder = None
    viewers = None

    def log_message(self, fmt, *a):
        pass  # one line per frame request would bury the useful log

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.serve_page()
        elif self.path == "/stream.mjpg":
            self.serve_stream()
        elif self.path == "/status.json":
            self.serve_status()
        else:
            self.send_error(404)

    def serve_page(self):
        host = socket.gethostname().split(".")[0]
        body = PAGE.format(host=host, width=self.args.width,
                           height=self.args.height, fps=self.args.fps,
                           scale=self.args.width * 2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_status(self):
        count, idle = self.viewers.snapshot()
        body = json.dumps({"viewers": count, "encoding": self.encoder.running,
                           "idle_seconds": round(idle, 1)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_stream(self):
        count = self.viewers.join()
        log(f"viewer connected ({count} watching)")
        self.encoder.start()
        write_status(self.args, self.encoder, self.viewers)

        # A small send buffer is deliberate. If the link hiccups, a large kernel
        # buffer would queue several stale frames and the viewer would fall
        # seconds behind; a small one makes us block instead, and blocking means
        # we skip ahead to the newest frame on the next pass.
        try:
            self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
        except OSError:
            pass

        self.send_response(200)
        self.send_header("Age", "0")
        self.send_header("Cache-Control", "no-cache, private")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Type",
                         "multipart/x-mixed-replace; boundary=FRAME")
        # An MJPEG stream has no Content-Length and isn't chunked, so under
        # HTTP/1.1 the only legal way to frame it is "body ends when the
        # connection closes". Without this the browser can't tell where the body
        # ends and may buffer indefinitely, showing nothing at all.
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        last_sent = 0
        try:
            while True:
                frame, sequence = self.broker.newest(after=last_sent)
                if frame is None:
                    if not self.encoder.running:
                        break
                    continue
                last_sent = sequence
                # One write per frame: several small writes would become several
                # packets, each adding a round of latency.
                self.wfile.write(
                    b"--FRAME\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n"
                )
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        finally:
            count = self.viewers.leave()
            log(f"viewer left ({count} watching)")
            write_status(self.args, self.encoder, self.viewers)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def idle_monitor(args, encoder, viewers, stop):
    """Stop the camera once nobody has watched for a while."""
    while not stop.wait(2.0):
        count, idle = viewers.snapshot()
        if count == 0 and encoder.running and idle > args.idle_timeout:
            encoder.stop()
        write_status(args, encoder, viewers)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--fps", type=int, default=24,
                        help="24 is smooth and fine for one or two robots. A "
                             "full class of 20 streaming at once needs about 5 "
                             "-- see the table in the README")
    parser.add_argument("--quality", type=int, default=0,
                        help="JPEG quality 1-100; 0 leaves it to rpicam-vid")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--idle-timeout", type=float, default=300.0,
                        help="seconds with no viewer before the camera releases")
    parser.add_argument("--hflip", action="store_true")
    parser.add_argument("--vflip", action="store_true")
    args = parser.parse_args()

    if not shutil.which("rpicam-vid"):
        sys.exit("rpicam-vid not found -- this needs Raspberry Pi OS")

    broker = Broker()
    viewers = Viewers()
    encoder = Encoder(args, broker)

    Handler.args = args
    Handler.broker = broker
    Handler.encoder = encoder
    Handler.viewers = viewers

    try:
        httpd = Server(("0.0.0.0", args.port), Handler)
    except OSError as exc:
        sys.exit(f"can't listen on port {args.port}: {exc}")

    with open(PID_FILE, "w") as handle:
        handle.write(f"{os.getpid()} {args.port}\n")

    stop = threading.Event()
    monitor = threading.Thread(target=idle_monitor,
                               args=(args, encoder, viewers, stop), daemon=True)
    monitor.start()
    write_status(args, encoder, viewers)

    host = socket.gethostname().split(".")[0]
    log(f"serving http://{host}.local:{args.port}/ "
        f"({args.width}x{args.height} @ {args.fps}fps, "
        f"camera idles out after {args.idle_timeout:.0f}s)")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        encoder.stop()
        httpd.server_close()
        for path in (PID_FILE, STATUS_FILE):
            try:
                os.remove(path)
            except OSError:
                pass
        log("stopped")


if __name__ == "__main__":
    main()

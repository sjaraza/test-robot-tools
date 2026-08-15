#!/usr/bin/env python3
"""Read the robot's camera stream and run computer vision on it. LAPTOP side.

    ./cvclient.py 1                 # robot-1, show faces
    ./cvclient.py 1 --detect none    # just view, measure latency
    ./cvclient.py 1 --detect motion  # frame differencing
    ./cvclient.py 1 --no-window      # headless, print detections

Needs OpenCV on the laptop:

    pip install opencv-python                 # any OS
    sudo apt install python3-opencv           # Ubuntu / the VM

Everything heavy happens here, not on the robot. The robot only captures and
hardware-encodes; a Pi Zero 2 W has four slow cores and 512MB, and Haar cascades
would crawl there.

Latency note: this deliberately does NOT use cv2.VideoCapture. That buffers
frames internally, so if your CV is slower than the stream you fall further and
further behind until the picture is seconds stale. Instead a reader thread keeps
only the newest frame and older ones are dropped on the floor -- which is the
correct trade for live control.
"""

import argparse
import socket
import sys
import threading
import time
import urllib.request

try:
    import cv2
    import numpy as np
except ImportError:
    sys.exit("OpenCV is missing. Install it with:\n"
             "    pip install opencv-python\n"
             "  or, on Ubuntu:  sudo apt install python3-opencv")


# ---------------------------------------------------------------------------
# THIS IS THE PART YOU EDIT
# ---------------------------------------------------------------------------

def process_frame(frame, state, detector):
    """Called on the newest frame. Return the image to display.

    `frame`    BGR numpy array, safe to draw on
    `state`    a dict that persists between frames -- remember things in it
    `detector` whatever --detect selected, or None
    """
    return detector(frame, state) if detector else frame


# ---------------------------------------------------------------------------
# detectors
# ---------------------------------------------------------------------------

def make_face_detector():
    """Haar cascade face detection. The classic 'my robot can see' demo."""
    path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(path)
    if cascade.empty():
        sys.exit(f"couldn't load the cascade from {path}")

    def detect(frame, state):
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # equalizeHist makes it far more robust to the robot's auto-exposure
        # swinging around as it drives.
        grey = cv2.equalizeHist(grey)
        faces = cascade.detectMultiScale(grey, scaleFactor=1.2, minNeighbors=4,
                                         minSize=(24, 24))
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            centre = x + w // 2
            cv2.circle(frame, (centre, y + h // 2), 3, (0, 255, 0), -1)
        state["faces"] = [(int(x), int(y), int(w), int(h)) for x, y, w, h in faces]
        return frame

    return detect


def make_motion_detector():
    """Frame differencing. Cheap, and shows what 'state' is for."""
    def detect(frame, state):
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        grey = cv2.GaussianBlur(grey, (5, 5), 0)
        previous = state.get("previous")
        state["previous"] = grey
        if previous is None:
            return frame

        delta = cv2.absdiff(previous, grey)
        _, mask = cv2.threshold(delta, 20, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        moved = []
        for contour in contours:
            if cv2.contourArea(contour) < 120:      # ignore sensor noise
                continue
            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 200, 255), 2)
            moved.append((x, y, w, h))
        state["motion"] = moved
        return frame

    return detect


DETECTORS = {
    "faces": make_face_detector,
    "motion": make_motion_detector,
    "none": lambda: None,
}


# ---------------------------------------------------------------------------
# reading the stream
# ---------------------------------------------------------------------------

class NewestFrame:
    """Holds the most recent JPEG. Older frames are dropped, on purpose."""

    def __init__(self):
        self.jpeg = None
        self.stamp = 0.0
        self.count = 0
        self.lock = threading.Lock()
        self.error = None

    def put(self, jpeg):
        with self.lock:
            self.jpeg = jpeg
            self.stamp = time.monotonic()
            self.count += 1

    def take(self):
        """Return (jpeg, age_seconds) or (None, 0)."""
        with self.lock:
            if self.jpeg is None:
                return None, 0.0
            jpeg, stamp = self.jpeg, self.stamp
            self.jpeg = None          # don't re-process the same frame
        return jpeg, time.monotonic() - stamp


def reader(url, newest, stop):
    """Pull the multipart MJPEG stream, splitting it into JPEGs.

    Scanning for the JPEG markers is safe here: 0xFF bytes inside compressed
    data are byte-stuffed as 0xFF00, so a bare 0xFFD9 only ever means
    end-of-image.
    """
    SOI, EOI = b"\xff\xd8", b"\xff\xd9"
    try:
        with urllib.request.urlopen(url, timeout=10) as stream:
            buffer = bytearray()
            while not stop.is_set():
                chunk = stream.read(8192)
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
                    newest.put(bytes(buffer[start:end + 2]))
                    del buffer[:end + 2]
    except Exception as exc:
        newest.error = exc


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("robot", nargs="?", default="1",
                        help="robot number, e.g. 3 (default 1)")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--detect", choices=sorted(DETECTORS), default="faces")
    parser.add_argument("--no-window", action="store_true")
    args = parser.parse_args()

    host = args.robot if not args.robot.isdigit() else f"robot-{args.robot}"
    if not host.endswith(".local"):
        host += ".local"
    url = f"http://{host}:{args.port}/stream.mjpg"

    print(f"robot   : {host}")
    print(f"stream  : {url}")
    print(f"detect  : {args.detect}")
    print("q or Esc in the window to quit, or Ctrl-C\n")

    newest = NewestFrame()
    stop = threading.Event()
    thread = threading.Thread(target=reader, args=(url, newest, stop), daemon=True)
    thread.start()

    detector_factory = DETECTORS[args.detect]
    detector = detector_factory()
    state = {}

    processed = 0
    window_started = time.monotonic()
    shown_fps = 0.0
    waited = 0.0

    try:
        while True:
            if newest.error is not None:
                print(f"\nstream error: {newest.error}", file=sys.stderr)
                print(f"Is the stream on? Open http://{host}:{args.port}/ in a "
                      "browser,\nor start it from the robot's cockpit menu, "
                      "item 7.", file=sys.stderr)
                return 1

            jpeg, age = newest.take()
            if jpeg is None:
                time.sleep(0.005)
                waited += 0.005
                if waited > 15 and processed == 0:
                    print("no frames after 15s -- is the stream running?",
                          file=sys.stderr)
                    return 1
                continue

            frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8),
                                 cv2.IMREAD_COLOR)
            if frame is None:
                continue

            started = time.monotonic()
            frame = process_frame(frame, state, detector)
            cv_ms = (time.monotonic() - started) * 1000

            processed += 1
            elapsed = time.monotonic() - window_started
            if elapsed >= 1.0:
                shown_fps = processed / elapsed
                processed, window_started = 0, time.monotonic()

            if args.no_window:
                if state.get("faces"):
                    print(f"faces: {state['faces']}")
                elif state.get("motion"):
                    print(f"motion regions: {len(state['motion'])}")
                continue

            # age is how stale the frame was when we picked it up: the honest
            # measure of end-to-end lag from the robot to this loop.
            cv2.putText(frame, f"{shown_fps:4.1f} fps  cv {cv_ms:4.1f}ms  "
                               f"age {age * 1000:4.0f}ms",
                        (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
            cv2.imshow(host, frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    sys.exit(main())

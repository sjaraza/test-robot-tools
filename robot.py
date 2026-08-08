#!/usr/bin/env python3
"""Connect to a robot over SSH and drive it from a menu.

Run this on your own laptop:

    python3 robot.py

It asks which robot you want, your username, and your password, then shows a
menu: measure distance, drive, steer, pan/tilt the camera, read the line
sensors.

Nothing to install. Your laptop needs Python 3 and `ssh`, both of which macOS
and Windows 10/11 already have. All the robot code lives on the robot.
"""

import argparse
import atexit
import os
import shutil
import subprocess
import sys
import tempfile

DEFAULT_USER = "robot"
HELPER = "robot_actions.py"          # sits next to this file
REMOTE_HELPER = "/tmp/robot_actions.py"

GREEN = "\033[32m"
RED = "\033[31m"
BOLD = "\033[1m"
DIM = "\033[2m"
OFF = "\033[0m"

# 5-row block font, only the characters "ROBOT-0123456789" need to exist.
FONT = {
    "R": ("████ ", "█   █", "████ ", "█  █ ", "█   █"),
    "O": (" ███ ", "█   █", "█   █", "█   █", " ███ "),
    "B": ("████ ", "█   █", "████ ", "█   █", "████ "),
    "T": ("█████", "  █  ", "  █  ", "  █  ", "  █  "),
    "-": ("     ", "     ", " ███ ", "     ", "     "),
    "0": (" ███ ", "█  ██", "█ █ █", "██  █", " ███ "),
    "1": ("  █  ", " ██  ", "  █  ", "  █  ", " ███ "),
    "2": (" ███ ", "█   █", "   █ ", "  █  ", "█████"),
    "3": ("████ ", "    █", " ███ ", "    █", "████ "),
    "4": ("█   █", "█   █", "█████", "    █", "    █"),
    "5": ("█████", "█    ", "████ ", "    █", "████ "),
    "6": (" ███ ", "█    ", "████ ", "█   █", " ███ "),
    "7": ("█████", "    █", "   █ ", "  █  ", " █   "),
    "8": (" ███ ", "█   █", " ███ ", "█   █", " ███ "),
    "9": (" ███ ", "█   █", " ████", "    █", " ███ "),
}


def supports_colour():
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        # Windows Terminal and PowerShell 7 handle ANSI; old conhost doesn't.
        return os.environ.get("WT_SESSION") or os.environ.get("TERM")
    return True


COLOUR = supports_colour()


def paint(text, *codes):
    if not COLOUR:
        return text
    return "".join(codes) + text + OFF


def banner(text):
    """Print `text` as block letters."""
    rows = ["" for _ in range(5)]
    for char in text.upper():
        glyph = FONT.get(char)
        if glyph is None:
            continue
        for i in range(5):
            rows[i] += glyph[i] + " "
    print()
    for row in rows:
        print("  " + paint(row, BOLD, GREEN))
    print()


# ---------------------------------------------------------------------------
# ssh
# ---------------------------------------------------------------------------

class Robot:
    """One SSH connection to one robot, reused for every command.

    Uses OpenSSH connection multiplexing: we authenticate once (ssh prompts for
    the password itself -- this script never sees it), then every later command
    rides the same connection with no further prompting.
    """

    def __init__(self, target):
        self.target = target
        self.socket = None
        self._tempdir = None

    @property
    def host(self):
        return self.target.split("@", 1)[-1]

    def base_options(self):
        return [
            "-o", "ConnectTimeout=10",
            "-o", "StrictHostKeyChecking=accept-new",
        ]

    def connect(self):
        """Authenticate once. Returns True on success."""
        self._tempdir = tempfile.mkdtemp(prefix="robotcli-")
        self.socket = os.path.join(self._tempdir, "cm")

        cmd = [
            "ssh", "-M", "-S", self.socket,
            "-o", "ControlPersist=600",
            *self.base_options(),
            "-N", "-f", self.target,
        ]
        print(f"connecting to {paint(self.host, BOLD)} ...")
        result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            self.socket = None
            self._report_failure(stderr)
            return False

        atexit.register(self.close)
        return True

    def _report_failure(self, stderr):
        if stderr:
            print(stderr, file=sys.stderr)
        if "REMOTE HOST IDENTIFICATION HAS CHANGED" in stderr:
            print(
                f"\n{self.host} has a different SSH identity than last time.\n"
                "That's normal if its SD card was reimaged. Clear it and retry:\n\n"
                f"    ssh-keygen -R {self.host}\n",
                file=sys.stderr,
            )
        elif "Permission denied" in stderr:
            print("\nWrong username or password. Try again.", file=sys.stderr)
        elif "Could not resolve" in stderr or "Name or service" in stderr:
            print(f"\nCan't find {self.host} on the network. Check the robot is\n"
                  "powered on and joined to the same WiFi.", file=sys.stderr)

    def run(self, command, stdin=None, capture=True):
        """Run a shell command on the robot over the shared connection."""
        cmd = ["ssh", "-S", self.socket, *self.base_options(),
               self.target, command]
        if capture:
            return subprocess.run(cmd, input=stdin, capture_output=True, text=True)
        return subprocess.run(cmd, input=stdin, text=True)

    def upload(self, local_path, remote_path):
        """Copy a file over the existing connection, no scp needed."""
        with open(local_path, "r", encoding="utf-8") as handle:
            content = handle.read()
        return self.run(f"cat > {remote_path}", stdin=content)

    def close(self):
        if self.socket and os.path.exists(self.socket):
            subprocess.run(["ssh", "-S", self.socket, "-O", "exit", self.target],
                           capture_output=True)
        self.socket = None
        if self._tempdir and os.path.isdir(self._tempdir):
            shutil.rmtree(self._tempdir, ignore_errors=True)
            self._tempdir = None


# ---------------------------------------------------------------------------
# prompts
# ---------------------------------------------------------------------------

def ask(prompt, default=None):
    try:
        value = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit("cancelled")
    return value or default


def ask_number(prompt, low, high, default=None):
    """Ask for an integer in [low, high], re-asking until it's valid."""
    while True:
        raw = ask(prompt, str(default) if default is not None else None)
        if raw is None or raw == "":
            continue
        try:
            value = int(raw)
        except ValueError:
            print(f"  '{raw}' isn't a number")
            continue
        if low <= value <= high:
            return value
        print(f"  needs to be between {low} and {high}")


def prompt_for_robot():
    while True:
        value = ask("Which robot? (just the number, e.g. 3): ") or ""
        value = value.removeprefix("robot-").removesuffix(".local")
        if value.isdigit() and int(value) > 0:
            return value
        if value:
            print(f"  '{value}' doesn't look like a robot number -- try 1, 2, 3 ...")


# ---------------------------------------------------------------------------
# menu actions
# ---------------------------------------------------------------------------

def action(robot, name, *params):
    """Call the helper script on the robot and show what it says."""
    args = " ".join(str(p) for p in params)
    result = robot.run(f"python3 {REMOTE_HELPER} {name} {args}")
    output = (result.stdout or "").strip()
    errors = (result.stderr or "").strip()
    if output:
        print(output)
    if errors:
        print(paint(errors, RED), file=sys.stderr)
    return result.returncode == 0


def do_distance(robot):
    print("\nMeasuring distance ...")
    action(robot, "distance")


def do_drive(robot):
    print("\nDrive the car. Speed is 0-100, time is in seconds.")
    direction = ask("  forward or backward? [forward]: ", "forward").lower()
    if direction.startswith("b"):
        direction = "backward"
    else:
        direction = "forward"
    speed = ask_number("  speed (0-100) [30]: ", 0, 100, 30)
    seconds = ask_number("  for how many seconds (1-10) [2]: ", 1, 10, 2)
    print(f"  {direction} at {speed} for {seconds}s ...")
    action(robot, "drive", direction, speed, seconds)


def do_steer(robot):
    print("\nSteering angle. -30 is full left, 0 straight, 30 full right.")
    angle = ask_number("  angle (-30 to 30) [0]: ", -30, 30, 0)
    action(robot, "steer", angle)


def do_pan_tilt(robot):
    print("\nPoint the camera. Pan is left/right, tilt is up/down.")
    pan = ask_number("  pan (-90 to 90) [0]: ", -90, 90, 0)
    tilt = ask_number("  tilt (-35 to 65) [0]: ", -35, 65, 0)
    action(robot, "pantilt", pan, tilt)


def do_line_sensors(robot):
    print("\nReading the line-following sensors ...")
    action(robot, "grayscale")


def do_stop(robot):
    action(robot, "stop")


def do_shell(robot):
    command = ask("\n  command to run on the robot: ")
    if not command:
        return
    result = robot.run(command)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(paint(result.stderr.rstrip(), RED), file=sys.stderr)


MENU = [
    ("Measure distance", do_distance),
    ("Move the car", do_drive),
    ("Steer the wheels", do_steer),
    ("Pan / tilt the camera", do_pan_tilt),
    ("Read the line sensors", do_line_sensors),
    ("Stop everything", do_stop),
    ("Run any command on the robot", do_shell),
]


def show_menu(robot):
    while True:
        print()
        print(paint(f"  {robot.host}", BOLD))
        for index, (label, _) in enumerate(MENU, start=1):
            print(f"    {index}. {label}")
        print(f"    q. Quit")

        choice = ask("\n  choose: ")
        if choice is None:
            return
        if choice.lower() in ("q", "quit", "exit"):
            return
        if not choice.isdigit() or not 1 <= int(choice) <= len(MENU):
            print(f"  pick 1-{len(MENU)}, or q to quit")
            continue

        _, handler = MENU[int(choice) - 1]
        try:
            handler(robot)
        except KeyboardInterrupt:
            print("\n  interrupted -- stopping the car")
            do_stop(robot)


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("robot", nargs="?", help="robot number, e.g. 3")
    parser.add_argument("--user", help="login name")
    args = parser.parse_args()

    number = args.robot or prompt_for_robot()
    user = args.user or ask(f"Username [{DEFAULT_USER}]: ", DEFAULT_USER)
    target = f"{user}@robot-{number}.local"

    robot = Robot(target)
    if not robot.connect():
        sys.exit(1)

    banner(f"ROBOT-{number}")
    print("  " + paint("* SSH connection established", GREEN, BOLD))
    print("  " + paint(f"  logged in to {target}", DIM))

    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), HELPER)
    if not os.path.exists(helper):
        sys.exit(f"\ncan't find {HELPER} next to this script")

    result = robot.upload(helper, REMOTE_HELPER)
    if result.returncode != 0:
        print(paint("\ncouldn't copy the helper script to the robot:", RED),
              file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    # Ask the robot what hardware it can actually reach, so a missing library
    # shows up now with a clear message instead of on the first menu action.
    probe = robot.run(f"python3 {REMOTE_HELPER} probe")
    if probe.stdout.strip():
        print("  " + paint(probe.stdout.strip().replace("\n", "\n  "), DIM))
    if probe.returncode != 0:
        print(paint((probe.stderr or "").strip(), RED), file=sys.stderr)

    try:
        show_menu(robot)
    finally:
        do_stop(robot)
        robot.close()
        print("\nbye")


if __name__ == "__main__":
    main()

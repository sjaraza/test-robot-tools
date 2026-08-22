#!/usr/bin/env python3
"""Robot control menu. Runs on the robot itself.

    robotmenu.py              open the dashboard and menu
    robotmenu.py --splash     print the login splash (used by install.sh)
    robotmenu.py --probe      report what hardware we can reach, and exit

Standard library only -- no pip installs. The PiCar-X libraries are imported
lazily, so the dashboard still works on a robot whose hardware is missing or
misbehaving.
"""

import argparse
import contextlib
import os
import shutil
import socket
import subprocess
import sys
import time
import warnings


@contextlib.contextmanager
def quiet():
    """Silence library chatter while we read the hardware.

    robot_hat emits DeprecationWarnings, and anything printed while the frame is
    being drawn lands in the middle of it. Redirect at the file-descriptor level
    so writes from C extensions are caught too, not just Python's warnings.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        saved = os.dup(2)
        devnull = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(devnull, 2)
            yield
        finally:
            os.dup2(saved, 2)
            os.close(devnull)
            os.close(saved)

# ---------------------------------------------------------------------------
# terminal helpers
# ---------------------------------------------------------------------------

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
GREY = "\033[90m"


def colour_enabled():
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


COLOUR = colour_enabled()

# 24-bit colour where the terminal admits to supporting it (iTerm2, Windows
# Terminal, most Linux terminals). macOS Terminal.app does not, hence the
# 256-colour fallback below.
TRUECOLOR = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")

# mint -> azure -> violet
GRADIENT = [(0, 255, 196), (0, 163, 255), (168, 85, 247)]


def rgb_to_256(rgb):
    """Nearest colour in xterm's 6x6x6 cube."""
    red, green, blue = (int(round(channel / 255 * 5)) for channel in rgb)
    return 16 + 36 * red + 6 * green + blue


def fg(rgb):
    if TRUECOLOR:
        return f"\033[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"
    return f"\033[38;5;{rgb_to_256(rgb)}m"


def lerp(start, end, t):
    return tuple(int(round(start[i] + (end[i] - start[i]) * t)) for i in range(3))


def gradient_colour(t, stops=GRADIENT):
    """Colour at position `t` (0..1) along a multi-stop gradient."""
    if t <= 0:
        return stops[0]
    if t >= 1:
        return stops[-1]
    segments = len(stops) - 1
    position = t * segments
    index = min(int(position), segments - 1)
    return lerp(stops[index], stops[index + 1], position - index)


def gradient_text(text, stops=GRADIENT, bold=False):
    """Colour `text` left-to-right along the gradient.

    Only emits an escape when the colour actually changes, and skips spaces, so
    a banner costs a few dozen escapes rather than one per character.
    """
    if not COLOUR:
        return text
    span = max(1, len(text) - 1)
    pieces = [BOLD] if bold else []
    previous = None
    for index, char in enumerate(text):
        if char == " ":
            pieces.append(char)
            continue
        colour = gradient_colour(index / span, stops)
        if colour != previous:
            pieces.append(fg(colour))
            previous = colour
        pieces.append(char)
    pieces.append(RESET)
    return "".join(pieces)


def paint(text, *codes):
    if not COLOUR or not codes:
        return text
    return "".join(codes) + text + RESET


def visible_length(text):
    """Length of `text` ignoring ANSI escape sequences."""
    length, i = 0, 0
    while i < len(text):
        if text[i] == "\033":
            while i < len(text) and text[i] != "m":
                i += 1
            i += 1
            continue
        length += 1
        i += 1
    return length


def clear_screen():
    if COLOUR:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# block font, for the splash and the dashboard header
# ---------------------------------------------------------------------------

FONT = {
    # 5x5 glyphs. The whole alphabet, not just ROBOT, because robots get named
    # robot-A as readily as robot-1 -- and a hostname with an unknown character
    # falls back to plain text, losing the banner entirely.
    "A": (" ███ ", "█   █", "█████", "█   █", "█   █"),
    "B": ("████ ", "█   █", "████ ", "█   █", "████ "),
    "C": (" ████", "█    ", "█    ", "█    ", " ████"),
    "D": ("████ ", "█   █", "█   █", "█   █", "████ "),
    "E": ("█████", "█    ", "████ ", "█    ", "█████"),
    "F": ("█████", "█    ", "████ ", "█    ", "█    "),
    "G": (" ████", "█    ", "█  ██", "█   █", " ████"),
    "H": ("█   █", "█   █", "█████", "█   █", "█   █"),
    "I": ("█████", "  █  ", "  █  ", "  █  ", "█████"),
    "J": ("█████", "   █ ", "   █ ", "█  █ ", " ██  "),
    "K": ("█   █", "█  █ ", "███  ", "█  █ ", "█   █"),
    "L": ("█    ", "█    ", "█    ", "█    ", "█████"),
    "M": ("█   █", "██ ██", "█ █ █", "█   █", "█   █"),
    "N": ("█   █", "██  █", "█ █ █", "█  ██", "█   █"),
    "O": (" ███ ", "█   █", "█   █", "█   █", " ███ "),
    "P": ("████ ", "█   █", "████ ", "█    ", "█    "),
    "Q": (" ███ ", "█   █", "█ █ █", "█  █ ", " ██ █"),
    "R": ("████ ", "█   █", "████ ", "█  █ ", "█   █"),
    "S": (" ████", "█    ", " ███ ", "    █", "████ "),
    "T": ("█████", "  █  ", "  █  ", "  █  ", "  █  "),
    "U": ("█   █", "█   █", "█   █", "█   █", " ███ "),
    "V": ("█   █", "█   █", "█   █", " █ █ ", "  █  "),
    "W": ("█   █", "█   █", "█ █ █", "██ ██", "█   █"),
    "X": ("█   █", " █ █ ", "  █  ", " █ █ ", "█   █"),
    "Y": ("█   █", " █ █ ", "  █  ", "  █  ", "  █  "),
    "Z": ("█████", "   █ ", "  █  ", " █   ", "█████"),
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


def block_letters(text):
    """Render `text` as 5-row block letters.

    Returns None if any character isn't in the font, so callers can fall back
    to plain text rather than printing a half-empty banner.
    """
    if not all(char in FONT for char in text.upper()):
        return None
    rows = ["" for _ in range(5)]
    for char in text.upper():
        glyph = FONT[char.upper()]
        for i in range(5):
            rows[i] += glyph[i] + " "
    return rows


def banner_rows(text):
    """Block letters if we can, otherwise a plain single line."""
    rows = block_letters(text)
    if rows is None:
        return [text]
    return rows


def robot_name():
    """ROBOT-3 from hostname robot-3. ROBOT_NAME overrides, for testing."""
    override = os.environ.get("ROBOT_NAME")
    if override:
        return override.upper()
    return socket.gethostname().split(".")[0].upper()


def print_splash():
    """The login banner. Written to /etc/motd by install.sh."""
    print()
    for row in banner_rows(robot_name()):
        print("  " + gradient_text(row, bold=True))
    print()
    print("  " + paint("Type", GREY) + paint("  cockpit   ", BOLD, CYAN)
          + paint("to take the controls.", GREY))
    print("  " + paint("Type", GREY) + paint("  robostat  ", BOLD, CYAN)
          + paint("to see the robot's stats.", GREY))
    print("  " + paint("Type", GREY) + paint("  update    ", BOLD, CYAN)
          + paint("to pull the latest code.", GREY))
    print()


# ---------------------------------------------------------------------------
# reading the robot's vital signs -- all from /proc and /sys, no dependencies
# ---------------------------------------------------------------------------

def read_first_line(path):
    try:
        with open(path, "r") as handle:
            return handle.readline().strip()
    except OSError:
        return None


def cpu_temperature():
    """Degrees C, or None."""
    raw = read_first_line("/sys/class/thermal/thermal_zone0/temp")
    if raw is None or not raw.lstrip("-").isdigit():
        return None
    return int(raw) / 1000.0


def load_average():
    raw = read_first_line("/proc/loadavg")
    if not raw:
        return None
    try:
        return float(raw.split()[0])
    except (ValueError, IndexError):
        return None


def uptime_seconds():
    raw = read_first_line("/proc/uptime")
    if not raw:
        return None
    try:
        return float(raw.split()[0])
    except (ValueError, IndexError):
        return None


def memory_used_total_mb():
    """(used_mb, total_mb) using MemAvailable, which is what actually matters."""
    total = available = None
    try:
        with open("/proc/meminfo", "r") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    available = int(line.split()[1])
                if total is not None and available is not None:
                    break
    except (OSError, ValueError, IndexError):
        return None
    if total is None or available is None:
        return None
    return ((total - available) / 1024.0, total / 1024.0)


def disk_used_total_gb():
    try:
        usage = shutil.disk_usage("/")
    except OSError:
        return None
    return (usage.used / 1024**3, usage.total / 1024**3)


def wifi_signal_dbm():
    """Signal level in dBm from /proc/net/wireless, or None."""
    try:
        with open("/proc/net/wireless", "r") as handle:
            lines = handle.readlines()
    except OSError:
        return None
    for line in lines[2:]:
        parts = line.split()
        if len(parts) >= 4:
            try:
                return float(parts[3].rstrip("."))
            except ValueError:
                continue
    return None


def ip_address():
    """Our address on the LAN, found without sending anything."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def throttled_state():
    """Undervoltage / throttling flags from vcgencmd, or None if unavailable.

    Bit 0 = undervoltage now, bit 3 = throttled now, bit 16 = undervoltage has
    happened since boot. Worth surfacing: a sagging battery shows up here first.
    """
    if not shutil.which("vcgencmd"):
        return None
    import subprocess
    try:
        result = subprocess.run(["vcgencmd", "get_throttled"],
                                capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or "=" not in result.stdout:
        return None
    try:
        value = int(result.stdout.strip().split("=")[1], 16)
    except ValueError:
        return None
    flags = []
    if value & 0x1:
        flags.append("undervoltage now")
    if value & 0x8:
        flags.append("throttled now")
    if value & 0x10000:
        flags.append("undervoltage earlier")
    return flags


# PiCar-X runs on two 18650 cells: roughly 8.4V charged, 6.4V empty.
BATTERY_FULL = 8.4
BATTERY_EMPTY = 6.4


_BATTERY_SOURCE = "not tried"


def battery_voltage():
    """Battery volts, or None. Tries the robot_hat APIs newest-first."""
    global _BATTERY_SOURCE
    with quiet():
        # Current API. The older utils.get_battery_voltage() warns about this.
        try:
            from robot_hat import device
            if hasattr(device, "get_battery_voltage"):
                _BATTERY_SOURCE = "robot_hat.device.get_battery_voltage()"
                return float(device.get_battery_voltage())
        except Exception:
            pass

        try:
            from robot_hat import utils
            if hasattr(utils, "get_battery_voltage"):
                _BATTERY_SOURCE = "robot_hat.utils.get_battery_voltage() (deprecated)"
                return float(utils.get_battery_voltage())
        except Exception:
            pass

        try:
            from robot_hat import ADC
            # PiCar-X reads the pack through a divider on A4.
            _BATTERY_SOURCE = "ADC('A4') x3 divider"
            return ADC("A4").read() / 4095.0 * 3.3 * 3
        except Exception:
            pass

    _BATTERY_SOURCE = "no working method"
    return None


def battery_percent(volts):
    if volts is None:
        return None
    span = BATTERY_FULL - BATTERY_EMPTY
    fraction = (volts - BATTERY_EMPTY) / span
    return max(0.0, min(1.0, fraction)) * 100.0


# ---------------------------------------------------------------------------
# the dashboard
# ---------------------------------------------------------------------------

def bar(fraction, width=10, good_high=True):
    """A ██████░░░░ meter, coloured by how healthy the value is."""
    if fraction is None:
        return paint("─" * width, GREY)
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    health = fraction if good_high else 1.0 - fraction
    colour = GREEN if health > 0.5 else (YELLOW if health > 0.2 else RED)
    return paint("█" * filled, colour) + paint("░" * (width - filled), GREY)

def format_uptime(seconds):
    if seconds is None:
        return "n/a"
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def dashboard_lines():
    """The status cells, as (label, value) pairs, already coloured.

    Every reading happens here, before anything is printed, so a chatty library
    can't scribble into the middle of the frame.
    """
    rows = []

    volts = battery_voltage()
    percent = battery_percent(volts)
    if volts is None:
        rows.append(("batt", paint("n/a", GREY)))
    else:
        colour = GREEN if percent > 50 else (YELLOW if percent > 20 else RED)
        rows.append(("batt", f"{paint(f'{volts:.2f}V', BOLD, colour)} "
                             f"{bar(percent / 100.0, 6)} {percent:.0f}%"))

    temp = cpu_temperature()
    if temp is None:
        rows.append(("temp", paint("n/a", GREY)))
    else:
        # The Zero 2 W starts throttling around 80 C.
        colour = GREEN if temp < 60 else (YELLOW if temp < 75 else RED)
        rows.append(("temp", f"{paint(f'{temp:.1f}°C', colour)} "
                             f"{bar(temp / 85.0, 6, good_high=False)}"))

    memory = memory_used_total_mb()
    if memory:
        used, total = memory
        rows.append(("mem", f"{used:.0f}/{total:.0f}MB "
                            f"{bar(used / total, 6, good_high=False)}"))

    load = load_average()
    if load is not None:
        rows.append(("load", f"{load:.2f}"))

    disk = disk_used_total_gb()
    if disk:
        used, total = disk
        rows.append(("disk", f"{used:.1f}/{total:.1f}GB "
                             f"{bar(used / total, 6, good_high=False)}"))

    signal = wifi_signal_dbm()
    if signal is not None:
        # -50 excellent, -70 usable, -80 marginal.
        fraction = max(0.0, min(1.0, (signal + 90) / 40.0))
        colour = GREEN if signal > -60 else (YELLOW if signal > -75 else RED)
        rows.append(("wifi", f"{paint(f'{signal:.0f}dBm', colour)} "
                             f"{bar(fraction, 6)}"))

    rows.append(("up", format_uptime(uptime_seconds())))

    flags = throttled_state()
    if flags:
        rows.append(("power", paint(", ".join(flags), RED, BOLD)))
    elif flags == []:
        rows.append(("power", paint("healthy", GREEN)))

    streaming, status = camera_state()
    if not streaming:
        rows.append(("cam", paint("off", GREY)))
    elif status.get("viewers"):
        watchers = status["viewers"]
        rows.append(("cam", paint(f"live · {watchers} watching", GREEN, BOLD)))
    else:
        rows.append(("cam", paint("on · idle", YELLOW)))

    # gethostname() may already carry a domain (macOS returns "name.local"),
    # so take the short form and add the suffix ourselves.
    short_host = socket.gethostname().split(".")[0]
    address = ip_address()
    rows.append(("host", f"{short_host}.local"
                         + (f"  {paint(address, GREY)}" if address else "")))

    return rows


def clip(text, width):
    """Cut `text` to `width` visible columns, keeping ANSI escapes intact.

    Needed because a long hostname or a long IP would otherwise push the frame's
    right-hand border out and the box would look broken. Counting visible
    characters means the colour codes don't consume any of the budget.
    """
    if visible_length(text) <= width:
        return text
    out = []
    visible = 0
    index = 0
    while index < len(text) and visible < width:
        if text[index] == "\033":            # copy the whole escape sequence
            while index < len(text) and text[index] != "m":
                out.append(text[index])
                index += 1
            if index < len(text):
                out.append(text[index])
                index += 1
            continue
        out.append(text[index])
        visible += 1
        index += 1
    clipped = "".join(out)
    # Only re-emit a reset if we actually cut through coloured text. Appending it
    # unconditionally puts a literal escape into --no-color output.
    if "\033" in clipped:
        clipped += RESET
    return clipped


def pad(text, width):
    """Fit `text` to exactly `width` visible columns: clip if long, pad if short."""
    text = clip(text, width)
    return text + " " * max(0, width - visible_length(text))


def cell(label, value, width):
    return pad(f"{paint(label.rjust(5), GREY)} {value}", width)


def draw(menu_items, message=None):
    # Read everything first. Nothing is printed until the frame is ready, so a
    # library that logs on import can't break the box.
    stats = dashboard_lines()

    width = min(shutil.get_terminal_size((72, 24)).columns, 72)
    inner = width - 4
    half = (inner - 2) // 2
    side = paint("│", fg(gradient_colour(0.5))) if COLOUR else "│"

    def line(content=""):
        print(side + " " + pad(content, inner) + " " + side)

    def rule(left="├", right="┤", fill="─"):
        print(gradient_text(left + fill * (width - 2) + right))

    clear_screen()
    print(gradient_text("╭" + "─" * (width - 2) + "╮"))
    for row in banner_rows(robot_name()):
        line(gradient_text(row, bold=True))
    rule()

    # Two columns, so the whole frame fits an 80x24 terminal without scrolling.
    for index in range(0, len(stats), 2):
        left_label, left_value = stats[index]
        left = cell(left_label, left_value, half)
        if index + 1 < len(stats):
            right_label, right_value = stats[index + 1]
            right = cell(right_label, right_value, half)
        else:
            right = ""
        line(left + "  " + right)
    rule()

    for index, (label, _) in enumerate(menu_items, start=1):
        # Right-align the number: with ten or more items, left-aligning shifts
        # every label by a column.
        line(f"  {paint(str(index).rjust(2), BOLD, CYAN)}  {label}")
    line(f"  {paint(' r', BOLD, CYAN)}  Refresh"
         f"{'':>4}{paint('q', BOLD, CYAN)}  Quit")
    print(gradient_text("╰" + "─" * (width - 2) + "╯"))

    if message:
        print(message)


# ---------------------------------------------------------------------------
# hardware
# ---------------------------------------------------------------------------

HOME_CHECKOUTS = (
    os.path.expanduser("~/picar-x"),
    os.path.expanduser("~/robot-hat"),
)

# The libraries live in ~, but picarx writes its calibration to a hardcoded
# /opt/picar-x. Both matter, for different reasons.
HARDWARE_DIRS = HOME_CHECKOUTS + ("/opt/picar-x",)


def add_home_checkouts_to_path():
    """Let `import picarx` find a checkout in the home directory.

    On these robots picar-x and robot-hat live in ~, not only site-packages, so
    add them if they're present. Harmless when the libraries are pip-installed.
    """
    for path in HOME_CHECKOUTS:
        for candidate in (path, os.path.join(path, "lib")):
            if os.path.isdir(candidate) and candidate not in sys.path:
                sys.path.append(candidate)


_car = None


def car():
    """The Picarx object, created once. Raises RuntimeError with a clear cause."""
    global _car
    if _car is not None:
        return _car
    try:
        from picarx import Picarx
    except Exception:
        add_home_checkouts_to_path()
        try:
            from picarx import Picarx
        except Exception as exc:
            raise RuntimeError(
                f"the picarx library isn't available ({exc}).\n"
                "  Install the PiCar-X software on this robot first."
            ) from exc
    try:
        with quiet():
            _car = Picarx()
    except PermissionError as exc:
        # picarx writes its servo calibration to a config file. If that path is
        # outside the home directory it will be root-owned and refuse us.
        path = getattr(exc, "filename", None) or "the picarx config directory"
        raise RuntimeError(
            f"no permission to write {path}.\n"
            "  PiCar-X keeps its calibration there. Fix it once, on the robot:\n\n"
            f"      sudo mkdir -p {path}\n"
            f"      sudo chown -R $USER:$USER {path}\n"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"picarx is installed but wouldn't start ({type(exc).__name__}: {exc}).\n"
            "  Check the robot-hat is seated and the battery switch is on."
        ) from exc
    return _car


def probe():
    """Report what we can and can't reach. Handy when something looks wrong."""
    add_home_checkouts_to_path()   # same paths the menu will use
    print(f"hostname          {socket.gethostname()}")
    print(f"python            {sys.version.split()[0]}")

    for module in ("picarx", "robot_hat"):
        try:
            imported = __import__(module)
            location = getattr(imported, "__file__", "?")
            print(f"{module:<17} ok   {location}")
        except Exception as exc:
            print(f"{module:<17} FAIL {exc}")

    volts = battery_voltage()
    print(f"battery           {f'{volts:.2f} V' if volts else 'unreadable'}"
          f"   via {_BATTERY_SOURCE}")
    temp = cpu_temperature()
    print(f"cpu temp          {f'{temp:.1f} °C' if temp else 'unreadable'}")
    print(f"vcgencmd          {shutil.which('vcgencmd') or 'missing'}")
    print(f"rpicam-vid        {shutil.which('rpicam-vid') or 'missing'}")

    for path in HARDWARE_DIRS:
        if not os.path.isdir(path):
            print(f"{path:<17} absent"
                  + ("  -- picarx needs this, run install.sh"
                     if path.startswith("/opt") else ""))
        elif os.access(path, os.W_OK):
            print(f"{path:<17} writable")
        else:
            print(f"{path:<17} NOT WRITABLE -- run: "
                  f"sudo chown -R $USER:$USER {path}")

    try:
        methods = [m for m in dir(car().__class__) if not m.startswith("_")]
        print(f"Picarx methods    {', '.join(sorted(methods))}")
    except RuntimeError as exc:
        print(f"Picarx            FAIL {exc}")


# ---------------------------------------------------------------------------
# menu actions
# ---------------------------------------------------------------------------

def ask(prompt, default=None):
    try:
        value = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    return value or default


def ask_number(prompt, low, high, default):
    while True:
        raw = ask(prompt, str(default))
        if raw is None:
            return None
        try:
            value = int(raw)
        except ValueError:
            print(f"  '{raw}' isn't a number")
            continue
        if low <= value <= high:
            return value
        print(f"  needs to be between {low} and {high}")


def status_line(text):
    """Overwrite the current terminal line instead of scrolling."""
    if sys.stdout.isatty():
        sys.stdout.write("\r\033[K" + text)
        sys.stdout.flush()
    else:
        print(text)


@contextlib.contextmanager
def keyboard():
    """Yield read_key(timeout) -> key name or None.

    Puts the terminal in cbreak mode so we see keys without waiting for Enter,
    and always restores it. Arrow keys arrive as escape sequences, so those get
    reassembled into 'up'/'down'/'left'/'right'. When stdin isn't a terminal the
    reader always returns None and Ctrl-C remains the way out.

    Reads the file descriptor directly rather than sys.stdin: a buffered text
    stream pulls the whole "\\x1b[A" burst into its own buffer, after which
    select() sees an empty fd and the arrow looks like a bare Esc.
    """
    if not sys.stdin.isatty():
        yield lambda timeout=0.1: None
        return

    import select
    import termios
    import tty

    descriptor = sys.stdin.fileno()
    saved = termios.tcgetattr(descriptor)

    ARROWS = {b"A": "up", b"B": "down", b"C": "right", b"D": "left"}

    def decode(data):
        """Last recognisable key in `data`.

        Arrow keys have two encodings and both turn up in practice: CSI
        ("\\x1b[A") in normal mode, and SS3 ("\\x1bOA") when the terminal is in
        application-cursor-keys mode, which readline and full-screen programs
        switch on. Handling only CSI made every arrow look like a bare Esc.

        Auto-repeat from a held key can deliver several sequences in one read;
        taking the last keeps the display in step with what's held down.
        """
        key = None
        index = 0
        while index < len(data):
            byte = data[index:index + 1]
            if byte == b"\x1b":
                introducer = data[index + 1:index + 2]
                if introducer in (b"[", b"O"):
                    final = data[index + 2:index + 3]
                    if final in ARROWS:
                        key = ARROWS[final]
                        index += 3
                        continue
                    # Some other escape sequence (function key, mouse report).
                    # Skip it rather than mistaking it for a keypress.
                    index += 3
                    continue
                key = "esc"
                index += 1
                continue
            if byte == b"\x03":
                raise KeyboardInterrupt
            if byte == b" ":
                key = "space"
            elif byte in (b"\r", b"\n"):
                key = "enter"
            else:
                key = byte.decode("utf-8", "replace").lower()
            index += 1
        return key

    def read_key(timeout=0.1):
        ready, _, _ = select.select([descriptor], [], [], timeout)
        if not ready:
            return None
        data = os.read(descriptor, 32)
        if not data:
            return None
        return decode(data)

    try:
        tty.setcbreak(descriptor)
        yield read_key
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, saved)


@contextlib.contextmanager
def any_key_watcher():
    """Yield a callable that's True once any key has been pressed.

    Ctrl-C isn't obvious to a 15-year-old, so live views stop on any keypress.
    """
    with keyboard() as read_key:
        yield lambda: read_key(0) is not None


def live_view(title, sample, interval=0.15, header=None):
    """Run `sample()` on a loop, showing one self-updating line.

    `sample` returns the text to display. Returning None ends the view.
    `header` is an optional fixed row printed directly above that line, for
    column labels. It has to be printed before the loop starts, because the
    loop keeps overwriting the one line it owns.
    """
    print(f"\n  {title}")
    print(f"  {paint('press any key to stop', GREY)}\n")
    if header is not None:
        print("  " + header)
    with any_key_watcher() as pressed:
        try:
            while not pressed():
                text = sample()
                if text is None:
                    break
                status_line("  " + text)
                time.sleep(interval)
        except KeyboardInterrupt:
            pass
    print()
    return True   # skip the "press enter" pause; the keypress was the input


def read_distance(px):
    """One raw reading in centimetres, or None if there's no ultrasonic API."""
    for name in ("get_distance", "ultrasonic"):
        target = getattr(px, name, None)
        if target is None:
            continue
        return target() if callable(target) else target.read()
    return None


# An HC-SR04-style sensor needs roughly 60ms of quiet between pings. Fire faster
# and the echo from the previous ping lands inside the next measurement window,
# which reads as wildly wrong distances rather than as noise.
PING_SPACING = 0.06
PING_SAMPLES = 3


def read_distance_stable(px, samples=PING_SAMPLES):
    """Median of several spaced readings.

    Returns (distance, used, spread):
      distance -- median of the valid readings, or -1 if none were valid
      used     -- how many of `samples` came back valid
      spread   -- max minus min, i.e. how much the sensor disagreed with itself

    A median rather than a mean because ultrasonic outliers are large and
    one-sided: a single missed echo would drag an average badly, but can't move
    the middle value.
    """
    values = []
    for _ in range(samples):
        time.sleep(PING_SPACING)
        reading = read_distance(px)
        if reading is None:
            return None, 0, 0.0
        if reading > 0:
            values.append(float(reading))
    if not values:
        return -1.0, 0, 0.0
    values.sort()
    return values[len(values) // 2], len(values), values[-1] - values[0]


def measure_distance():
    px = car()
    if read_distance(px) is None:
        print("\n  this robot exposes no ultrasonic reading")
        return False

    previous = [time.monotonic()]

    def sample():
        distance, used, spread = read_distance_stable(px)
        now = time.monotonic()
        elapsed = now - previous[0]
        previous[0] = now
        rate = 1.0 / elapsed if elapsed > 0 else 0.0

        if distance is None:
            return None
        if distance < 0:
            return paint("no echo — nothing in range", YELLOW)

        colour = RED if distance < 15 else (YELLOW if distance < 40 else GREEN)
        blocks = int(min(distance, 200) / 200 * 20)
        # spread is the honest confidence signal: small means the three pings
        # agreed, large means treat the number with suspicion.
        confidence = GREEN if spread < 2 else (YELLOW if spread < 10 else RED)
        return (f"{paint(f'{distance:6.1f} cm', BOLD, colour)}  "
                f"{paint('█' * blocks, colour)}{paint('░' * (20 - blocks), GREY)}  "
                f"{paint(f'±{spread:4.1f}', confidence)} "
                f"{paint(f'n={used}/{PING_SAMPLES}  {rate:3.1f}/s', GREY)}")

    return live_view("Distance  (median of 3 pings)", sample, interval=0.0)


LINE_LABELS = ("L", "C", "R")   # picarx reports the floor sensors left to right
LINE_COLUMN = 5                 # width each reading is padded to


def line_sensors():
    px = car()
    if not hasattr(px, "get_grayscale_data"):
        print("\n  this robot exposes no grayscale sensor API")
        return False

    def sample():
        values = px.get_grayscale_data()
        return "  ".join(paint(f"{v:{LINE_COLUMN}}", BOLD) for v in values)

    def label(index):
        if index < len(LINE_LABELS):
            return LINE_LABELS[index]
        return str(index + 1)

    # Header built from a real reading, so the labels can't outnumber or fall
    # short of the columns underneath them.
    header = "  ".join(
        paint(label(index).center(LINE_COLUMN), BOLD, CYAN)
        for index in range(len(px.get_grayscale_data()))
    )
    return live_view("Line sensors  (L left · C centre · R right)", sample,
                     interval=0.2, header=header)


MAX_STEER = 30          # picarx steering limit, degrees either side
DEAD_MAN = 0.45         # seconds without a keypress before the motors cut


# On these robots picarx's forward() drives the car backwards and backward()
# drives it forwards -- the motors are wired mirrored to what the library
# assumes. Rather than sprinkle that surprise through the menu, the two helpers
# below are named for what the car actually does, and are the only place the
# swap happens. Everything above them talks about real directions.
def drive_forward(px, speed):
    px.backward(speed)


def drive_backward(px, speed):
    px.forward(speed)


def drive_arrows():
    """Arrow-key teleop with a dead-man stop.

    Holding an arrow relies on the terminal's key auto-repeat: each repeat
    refreshes the timer, and DEAD_MAN seconds of silence stops the motors. That
    matters -- without it, releasing the key over a laggy SSH link would leave
    the car driving into a wall.
    """
    px = car()
    if not sys.stdin.isatty():
        print("\n  arrow-key driving needs a real terminal")
        return False

    print("\n  Drive with the arrow keys.")
    speed = ask_number("  speed (0-100) [10]: ", 0, 100, 10)
    if speed is None:
        return False
    steer_step = ask_number("  steer step in degrees (1-15) [1]: ", 1, 15, 1)
    if steer_step is None:
        return False

    angle = 0
    moving = None                  # 'forward' | 'backward' | None
    last_command = 0.0

    print()
    print(f"  {paint('↑', BOLD, CYAN)} forward   "
          f"{paint('↓', BOLD, CYAN)} back   "
          f"{paint('← →', BOLD, CYAN)} steer   "
          f"{paint('space', BOLD, CYAN)} stop")
    print(f"  {paint('+ -', BOLD, CYAN)} speed   "
          f"{paint('c', BOLD, CYAN)} centre wheels   "
          f"{paint('q', BOLD, CYAN)} back to the cockpit")
    print()

    try:
        with keyboard() as read_key:
            while True:
                key = read_key(0.08)
                now = time.monotonic()

                if key in ("q", "esc"):
                    break
                elif key == "up":
                    drive_forward(px, speed)
                    moving, last_command = "forward", now
                elif key == "down":
                    drive_backward(px, speed)
                    moving, last_command = "backward", now
                elif key == "left":
                    angle = max(-MAX_STEER, angle - steer_step)
                    px.set_dir_servo_angle(angle)
                elif key == "right":
                    angle = min(MAX_STEER, angle + steer_step)
                    px.set_dir_servo_angle(angle)
                elif key == "c":
                    angle = 0
                    px.set_dir_servo_angle(angle)
                elif key == "space":
                    px.stop()
                    moving = None
                elif key in ("+", "="):
                    speed = min(100, speed + 5)
                elif key in ("-", "_"):
                    speed = max(0, speed - 5)

                # Dead-man: no fresh command recently means stop.
                if moving and now - last_command > DEAD_MAN:
                    px.stop()
                    moving = None

                state = (paint(moving, BOLD, GREEN) if moving
                         else paint("stopped", GREY))
                # Scale the indicator to the full steering range, so it reads
                # the same whether the step is 1 degree or 15.
                marks = round(abs(angle) / MAX_STEER * 6)
                wheel = (("◀" * marks) if angle < 0 else ("▶" * marks)) or "•"
                status_line(f"  {state:<20} speed {paint(f'{speed:3}', BOLD)}   "
                            f"steer {paint(f'{angle:+3}', BOLD)}° "
                            f"{paint(wheel, CYAN)}")
    except KeyboardInterrupt:
        pass
    finally:
        # Whatever happened, do not leave the car driving.
        px.stop()
        px.set_dir_servo_angle(0)

    print()
    print("  stopped, wheels straightened")
    return True


def drive():
    px = car()
    print("\n  Drive for a set time. Speed 0-100, time in seconds.")
    direction = ask("  forward or backward? [forward]: ", "forward")
    if direction is None:
        return
    backward = direction.lower().startswith("b")
    speed = ask_number("  speed (0-100) [30]: ", 0, 100, 30)
    if speed is None:
        return
    seconds = ask_number("  seconds (1-10) [2]: ", 1, 10, 2)
    if seconds is None:
        return

    print(f"  {'backward' if backward else 'forward'} at {speed} "
          f"for {seconds}s ...")
    try:
        drive_backward(px, speed) if backward else drive_forward(px, speed)
        time.sleep(seconds)
    except KeyboardInterrupt:
        print("\n  interrupted")
    finally:
        # Always stop, whatever happened above.
        px.stop()
        print("  stopped")


def steer():
    px = car()
    print("\n  Steering. -30 full left, 0 straight, 30 full right.")
    angle = ask_number("  angle (-30 to 30) [0]: ", -30, 30, 0)
    if angle is None:
        return
    px.set_dir_servo_angle(angle)
    print(f"  wheels at {angle}°")


PAN_RANGE = (-90, 90)
TILT_RANGE = (-35, 65)


def pan_tilt():
    """Point the camera with the arrow keys."""
    px = car()
    if not sys.stdin.isatty():
        print("\n  pan/tilt needs a real terminal")
        return False

    pan = tilt = 0
    print("\n  Point the camera with the arrow keys.")
    step = ask_number("  step size in degrees (1-15) [1]: ", 1, 15, 1)
    if step is None:
        return False

    def apply():
        px.set_cam_pan_angle(pan)
        px.set_cam_tilt_angle(tilt)

    print()
    print(f"  {paint('← →', BOLD, CYAN)} pan   "
          f"{paint('↑ ↓', BOLD, CYAN)} tilt   "
          f"{paint('c', BOLD, CYAN)} centre   "
          f"{paint('q', BOLD, CYAN)} back to the cockpit")
    print()

    apply()
    try:
        with keyboard() as read_key:
            while True:
                key = read_key(0.08)
                if key in ("q", "esc"):
                    break
                elif key == "left":
                    pan = max(PAN_RANGE[0], pan - step)
                    apply()
                elif key == "right":
                    pan = min(PAN_RANGE[1], pan + step)
                    apply()
                elif key == "up":
                    tilt = min(TILT_RANGE[1], tilt + step)
                    apply()
                elif key == "down":
                    tilt = max(TILT_RANGE[0], tilt - step)
                    apply()
                elif key == "c":
                    pan = tilt = 0
                    apply()

                status_line(f"  pan {paint(f'{pan:+4}', BOLD)}°   "
                            f"tilt {paint(f'{tilt:+4}', BOLD)}°")
    except KeyboardInterrupt:
        pass

    print()
    print("  camera left where you pointed it")
    return True


CAM_PID_FILE = "/tmp/robotcam.pid"
CAM_STATUS_FILE = "/tmp/robotcam.status"
CAM_LOG_FILE = "/tmp/robotcam.log"


def camera_state():
    """(running, status_dict). status is {} when the stream isn't up."""
    try:
        with open(CAM_PID_FILE) as handle:
            pid = int(handle.read().split()[0])
    except (OSError, ValueError, IndexError):
        return False, {}
    try:
        os.kill(pid, 0)           # signal 0 just tests existence
    except OSError:
        return False, {}
    try:
        import json
        with open(CAM_STATUS_FILE) as handle:
            return True, json.load(handle)
    except (OSError, ValueError):
        return True, {}


def camera_url(status):
    if status.get("url"):
        return status["url"]
    port = status.get("port", 8080)
    return f"http://{socket.gethostname().split('.')[0]}.local:{port}/"


def stop_camera():
    import signal
    try:
        with open(CAM_PID_FILE) as handle:
            pid = int(handle.read().split()[0])
    except (OSError, ValueError, IndexError):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    for _ in range(30):
        time.sleep(0.1)
        try:
            os.kill(pid, 0)
        except OSError:
            return True
    return True


def robot_number():
    """The digits from this robot's hostname, for pasting into laptop commands.

    Falls back to the whole hostname so the command we print is still usable on
    a robot that isn't named robot-N.
    """
    host = socket.gethostname().split(".")[0]
    digits = "".join(char for char in host if char.isdigit())
    return digits or host


def camera_stream():
    """Toggle the browser stream on or off."""
    running, status = camera_state()

    if running:
        print(f"\n  Stream is on at {camera_url(status)}")
        answer = ask("  turn it off? [y/N]: ", "n")
        if answer and answer.lower().startswith("y"):
            stop_camera()
            print("  stream stopped, camera released")
        return False

    print("\n  Start the camera stream.")

    # A synthetic pattern splits "the stream is broken" into two questions: if
    # this shows up in the browser then the network, HTTP path and browser are
    # all fine and the camera is the problem.
    answer = ask("  use a test pattern instead of the camera? [y/N]: ", "n")
    dummy = bool(answer) and answer.lower().startswith("y")

    fps = 5
    grey = False
    if dummy:
        print("  " + paint("test pattern runs at a fixed 5fps -- it's drawn in",
                           GREY))
        print("  " + paint("Python, so a higher rate would just load the CPU.",
                           GREY))
    else:
        print("  " + paint("24fps suits one or two robots. Use about 5 if a whole",
                           GREY))
        print("  " + paint("class is streaming at once.", GREY))
        fps = ask_number("  fps (1-30) [24]: ", 1, 30, 24)
        if fps is None:
            return False
        print("  " + paint("greyscale is smaller and lower latency, and is what",
                           GREY))
        print("  " + paint("face detection uses anyway.", GREY))
        answer = ask("  greyscale? [y/N]: ", "n")
        grey = bool(answer) and answer.lower().startswith("y")

    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "camstream.py")
    if not os.path.exists(script):
        print(paint(f"  can't find {script}", RED))
        return False

    command = [sys.executable, script, "--fps", str(fps)]
    if dummy:
        command.append("--dummy")
    if grey:
        command.append("--grey")

    # start_new_session so the stream outlives this menu, and its own log file
    # so a failure to open the camera is recoverable after the fact.
    with open(CAM_LOG_FILE, "a") as log_handle:
        subprocess.Popen(
            command,
            stdout=log_handle, stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    for _ in range(40):
        time.sleep(0.1)
        running, status = camera_state()
        if running:
            break

    if not running:
        print(paint("  the stream didn't start. Last few log lines:", RED))
        print(tail_file(CAM_LOG_FILE, 8))
        return False

    print()
    print("  " + paint("stream is live", GREEN, BOLD)
          + (paint("  (test pattern, not the camera)", YELLOW) if dummy else ""))
    print("  watch it in a browser:")
    print("  " + paint(camera_url(status), BOLD, CYAN))
    print()
    # The cockpit runs here on the robot, but computer vision runs on the
    # student's laptop -- so the most useful thing we can do is hand them the
    # exact command, with this robot's name already filled in.
    print("  " + paint("to run computer vision, on YOUR LAPTOP or VM:", GREY))
    print("  " + paint(f"./cvclient.py {robot_number()}", BOLD, CYAN))
    print("  " + paint("(from the test-robot-lab repo)", GREY))
    print()
    print("  " + paint("The camera only encodes while something is watching,",
                       GREY))
    print("  " + paint("and releases itself after 5 idle minutes.", GREY))
    return False


def show_camera_log():
    """The stream's own log. First place to look when it won't play."""
    print()
    running, status = camera_state()
    if running:
        print("  " + paint(f"stream running at {camera_url(status)}", GREEN))
        if status:
            print("  " + paint(f"viewers={status.get('viewers', '?')}  "
                               f"encoding={status.get('encoding', '?')}  "
                               f"idle={status.get('idle_seconds', '?')}s", GREY))
    else:
        print("  " + paint("stream is not running", GREY))

    print()
    print("  " + paint(f"{CAM_LOG_FILE}  (last 25 lines)", GREY))
    print("  " + paint("─" * 50, GREY))
    text = tail_file(CAM_LOG_FILE, 25)
    if not text.strip():
        print("  (empty -- the stream has never been started)")
    else:
        for line in text.splitlines():
            print("  " + line)
    print("  " + paint("─" * 50, GREY))
    print()
    print("  " + paint("If the browser shows nothing, try the test pattern in", GREY))
    print("  " + paint("the camera menu: it proves whether the camera is at fault.", GREY))
    return False


def tail_file(path, lines):
    try:
        with open(path) as handle:
            return "".join(handle.readlines()[-lines:]).rstrip()
    except OSError:
        return "  (no log)"


def stop_everything():
    px = car()
    px.stop()
    px.set_dir_servo_angle(0)
    print("\n  stopped, wheels straightened")


def show_probe():
    print()
    probe()


MENU = [
    ("Drive with the arrow keys", drive_arrows),
    ("Measure distance", measure_distance),
    ("Drive for a set time", drive),
    ("Steer to an angle", steer),
    ("Point the camera (arrow keys)", pan_tilt),
    ("Read the line sensors", line_sensors),
    ("Camera stream on / off", camera_stream),
    ("Camera logs", show_camera_log),
    ("Stop everything", stop_everything),
    ("Diagnostics", show_probe),
]


def menu_loop():
    message = None
    while True:
        draw(MENU, message)
        message = None
        choice = ask("\n  choose: ")
        if choice is None or choice.lower() in ("q", "quit", "exit"):
            break
        if choice.lower() == "r":
            continue
        if not choice.isdigit() or not 1 <= int(choice) <= len(MENU):
            message = paint(f"  pick 1-{len(MENU)}, r to refresh, q to quit", YELLOW)
            continue

        _, handler = MENU[int(choice) - 1]
        skip_pause = False
        try:
            # Live views return True: the keypress that stopped them already
            # served as "I'm done looking at this".
            skip_pause = bool(handler())
        except RuntimeError as exc:
            print(paint(f"\n  {exc}", RED))
        except KeyboardInterrupt:
            print("\n  interrupted")
        if not skip_pause:
            ask("\n  press enter to go back ")

    # Never leave the motors running on the way out.
    try:
        car().stop()
    except Exception:
        pass
    print("\n  bye")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--splash", action="store_true",
                        help="print the login banner and exit")
    parser.add_argument("--probe", action="store_true",
                        help="report reachable hardware and exit")
    parser.add_argument("--color", action="store_true",
                        help="force colour even when output isn't a terminal "
                             "(install.sh needs this: it pipes through tee)")
    parser.add_argument("--no-color", action="store_true", help="disable colour")
    parser.add_argument("--truecolor", action="store_true",
                        help="force 24-bit colour in the splash (default is "
                             "256-colour, which every terminal handles)")
    args = parser.parse_args()

    global COLOUR, TRUECOLOR
    if args.color:
        COLOUR = True
    if args.no_color:
        COLOUR = False

    if args.splash:
        # The motd is baked once and then rendered by whatever terminal the
        # student happens to use, so default to the safe 256-colour palette.
        TRUECOLOR = args.truecolor
        print_splash()
        return
    if args.probe:
        probe()
        return
    menu_loop()


if __name__ == "__main__":
    main()

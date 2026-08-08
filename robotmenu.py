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
import os
import shutil
import socket
import sys
import time

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
    print("  " + paint("Type", GREY) + paint("  launch  ", BOLD, CYAN)
          + paint("to open the robot menu.", GREY))
    print("  " + paint("Type", GREY) + paint("  update  ", BOLD, CYAN)
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


def battery_voltage():
    """Battery volts, or None. Tries the robot_hat APIs in order of preference.

    NOTE: not yet verified against real hardware -- if the dashboard shows n/a,
    run `robotmenu.py --probe` to see which attempt failed and why.
    """
    try:
        from robot_hat import utils
        if hasattr(utils, "get_battery_voltage"):
            return float(utils.get_battery_voltage())
    except Exception:
        pass

    try:
        from robot_hat import ADC
        # PiCar-X reads the pack through a divider on A4.
        raw = ADC("A4").read()
        return raw / 4095.0 * 3.3 * 3
    except Exception:
        pass

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
    """The status rows, as (label, value) pairs already coloured."""
    rows = []

    volts = battery_voltage()
    percent = battery_percent(volts)
    if volts is None:
        rows.append(("battery", paint("n/a", GREY)
                     + paint("  (robot_hat not reachable)", GREY)))
    else:
        colour = GREEN if percent > 50 else (YELLOW if percent > 20 else RED)
        rows.append(("battery",
                     f"{paint(f'{volts:.2f} V', BOLD, colour)}  "
                     f"{bar(percent / 100.0)}  {percent:.0f}%"))

    temp = cpu_temperature()
    if temp is None:
        rows.append(("cpu temp", paint("n/a", GREY)))
    else:
        # The Zero 2 W starts throttling around 80 C.
        colour = GREEN if temp < 60 else (YELLOW if temp < 75 else RED)
        rows.append(("cpu temp", f"{paint(f'{temp:.1f} °C', colour)}  "
                                 f"{bar(temp / 85.0, good_high=False)}"))

    load = load_average()
    memory = memory_used_total_mb()
    if memory:
        used, total = memory
        rows.append(("memory", f"{used:.0f} / {total:.0f} MB  "
                               f"{bar(used / total, good_high=False)}"))
    if load is not None:
        rows.append(("load", f"{load:.2f}"))

    disk = disk_used_total_gb()
    if disk:
        used, total = disk
        rows.append(("disk", f"{used:.1f} / {total:.1f} GB  "
                             f"{bar(used / total, good_high=False)}"))

    signal = wifi_signal_dbm()
    if signal is not None:
        # -50 excellent, -70 usable, -80 marginal.
        fraction = max(0.0, min(1.0, (signal + 90) / 40.0))
        colour = GREEN if signal > -60 else (YELLOW if signal > -75 else RED)
        rows.append(("wifi", f"{paint(f'{signal:.0f} dBm', colour)}  "
                             f"{bar(fraction)}"))

    address = ip_address()
    # gethostname() may already carry a domain (macOS returns "name.local"),
    # so take the short form and add the suffix ourselves.
    short_host = socket.gethostname().split(".")[0]
    rows.append(("address", f"{short_host}.local"
                            + (f"  ({address})" if address else "")))
    rows.append(("uptime", format_uptime(uptime_seconds())))

    flags = throttled_state()
    if flags:
        rows.append(("power", paint(", ".join(flags), RED, BOLD)))
    elif flags == []:
        rows.append(("power", paint("healthy", GREEN)))

    return rows


def draw(menu_items, message=None):
    width = min(shutil.get_terminal_size((72, 24)).columns, 72)
    inner = width - 4
    side = paint("│", fg(gradient_colour(0.5))) if COLOUR else "│"

    def line(content=""):
        pad = inner - visible_length(content)
        print(side + " " + content + " " * max(0, pad) + " " + side)

    def rule(left="├", right="┤", fill="─"):
        print(gradient_text(left + fill * (width - 2) + right))

    clear_screen()
    print(gradient_text("╭" + "─" * (width - 2) + "╮"))
    for row in banner_rows(robot_name()):
        line(gradient_text(row, bold=True))
    rule()

    for label, value in dashboard_lines():
        line(f"{paint(label.ljust(9), GREY)} {value}")
    rule()

    for index, (label, _) in enumerate(menu_items, start=1):
        line(f"  {paint(str(index), BOLD, CYAN)}  {label}")
    line(f"  {paint('r', BOLD, CYAN)}  Refresh")
    line(f"  {paint('q', BOLD, CYAN)}  Quit")
    print(gradient_text("╰" + "─" * (width - 2) + "╯"))

    if message:
        print(message)


# ---------------------------------------------------------------------------
# hardware
# ---------------------------------------------------------------------------

_car = None


def car():
    """The Picarx object, created once. Raises RuntimeError with a clear cause."""
    global _car
    if _car is not None:
        return _car
    try:
        from picarx import Picarx
    except Exception as exc:
        raise RuntimeError(
            f"the picarx library isn't available ({exc}).\n"
            "  Install the PiCar-X software on this robot first."
        ) from exc
    try:
        _car = Picarx()
    except Exception as exc:
        raise RuntimeError(
            f"picarx is installed but the hardware didn't respond ({exc}).\n"
            "  Check the robot-hat is seated and the battery switch is on."
        ) from exc
    return _car


def probe():
    """Report what we can and can't reach. Handy when something looks wrong."""
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
    print(f"battery           {f'{volts:.2f} V' if volts else 'unreadable'}")
    temp = cpu_temperature()
    print(f"cpu temp          {f'{temp:.1f} °C' if temp else 'unreadable'}")
    print(f"vcgencmd          {shutil.which('vcgencmd') or 'missing'}")
    print(f"rpicam-vid        {shutil.which('rpicam-vid') or 'missing'}")

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


def measure_distance():
    px = car()
    print("\n  Measuring. Ctrl-C to stop.\n")
    try:
        while True:
            distance = None
            for name in ("get_distance", "ultrasonic"):
                target = getattr(px, name, None)
                if target is None:
                    continue
                distance = target() if callable(target) else target.read()
                break
            if distance is None:
                print("  no ultrasonic reading available")
                return
            if distance < 0:
                print("  no echo (out of range?)")
            else:
                blocks = int(min(distance, 100) / 2)
                colour = RED if distance < 15 else (YELLOW if distance < 40 else GREEN)
                print(f"  {paint(f'{distance:6.1f} cm', BOLD, colour)} "
                      f"{paint('█' * blocks, colour)}")
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\n  stopped")


def drive():
    px = car()
    print("\n  Drive. Speed 0-100, time in seconds.")
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
        px.backward(speed) if backward else px.forward(speed)
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


def pan_tilt():
    px = car()
    print("\n  Camera. Pan is left/right, tilt is up/down.")
    pan = ask_number("  pan (-90 to 90) [0]: ", -90, 90, 0)
    if pan is None:
        return
    tilt = ask_number("  tilt (-35 to 65) [0]: ", -35, 65, 0)
    if tilt is None:
        return
    px.set_cam_pan_angle(pan)
    px.set_cam_tilt_angle(tilt)
    print(f"  camera at pan {pan}°, tilt {tilt}°")


def line_sensors():
    px = car()
    print("\n  Line sensors. Ctrl-C to stop.\n")
    try:
        while True:
            values = px.get_grayscale_data()
            print("  " + "  ".join(f"{v:5}" for v in values))
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\n  stopped")
    except AttributeError:
        print("  this robot has no grayscale sensor API")


def stop_everything():
    px = car()
    px.stop()
    px.set_dir_servo_angle(0)
    print("\n  stopped, wheels straightened")


def show_probe():
    print()
    probe()


MENU = [
    ("Measure distance", measure_distance),
    ("Move the car", drive),
    ("Steer the wheels", steer),
    ("Pan / tilt the camera", pan_tilt),
    ("Read the line sensors", line_sensors),
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
        try:
            handler()
        except RuntimeError as exc:
            print(paint(f"\n  {exc}", RED))
        except KeyboardInterrupt:
            print("\n  interrupted")
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

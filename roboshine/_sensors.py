"""Reading the sensors. Shared by roboshine and the cockpit.

Both used to read these themselves -- the cockpit talking to picarx directly and
roboshine wrapping the same calls -- which meant the L/C/R ordering was asserted
in two files and the ultrasonic timing rules were implemented twice, once with a
sleep in it. One copy each now, so the menu and a student's script can't disagree
about what the robot can see.

Nothing here blocks. The ultrasonic sensor needs quiet between pings, and that is
honoured by *not pinging* when it's too soon rather than by sleeping until it's
allowed -- see Distance below.
"""

import time

# The three floor sensors, in the order picarx reports them. robot-hat's own
# Grayscale_Module declares LEFT = 0, MIDDLE = 1, RIGHT = 2, and reads them in
# that order, which is where this ordering comes from. Which *physical* sensor is
# plugged into which channel is a wiring question -- check_line_sensors() below is
# how you find out.
LINE_KEYS = ("L", "C", "R")

# Readings are 12-bit ADC counts (robot_hat/adc.py returns 0-4095). Two useful
# figures from SunFounder's own robot_hat/modules.py, on the same hardware:
#
#   LINE_DIFF       = 200   how far apart the readings must be before they mean
#                           anything -- below this they're just noise
#   CLIFF_THRESHOLD = 120   under this there's no floor under that sensor at all
#
# Neither is used here: this module hands back numbers and lets the caller judge
# them. They're recorded because they're better starting points than a guess, and
# because "is there even a line" is the judgement students get wrong first.
ADC_MAX = 4095
LINE_DIFF = 200
CLIFF_THRESHOLD = 120

# An HC-SR04-style sensor needs roughly 60ms of quiet between pings. Fire faster
# and the echo from the previous ping arrives inside the next measurement window,
# which reads as wildly wrong distances rather than as noise.
PING_SPACING = 0.06
PING_SAMPLES = 3

# How long a distance reading is worth remembering. On a moving robot an older one
# is a measurement of somewhere else.
PING_MEMORY = 0.5


class NoSensor(RuntimeError):
    """That sensor isn't fitted, or this library can't reach it."""


def _sample_line(car, smooth):
    """`smooth` back-to-back readings per sensor, each channel's sorted."""
    reader = getattr(car, "get_grayscale_data", None)
    if reader is None:
        raise NoSensor("this robot has no line sensors fitted")

    collected = {key: [] for key in LINE_KEYS}
    for _ in range(max(1, int(smooth))):
        values = reader()
        if not values or len(values) < 3:
            raise RuntimeError(f"expected three sensor readings, got {values!r}")
        for key, value in zip(LINE_KEYS, values[:3]):
            collected[key].append(int(value))

    return {key: sorted(values) for key, values in collected.items()}


def read_line(car, smooth=1):
    """The three floor sensors as {'L': .., 'C': .., 'R': ..}.

    Lower numbers are darker. Raises NoSensor if there are no line sensors.

    `smooth` is how many readings to take and take the middle of. 1 is the raw
    sensor, warts and all. More than that filters out the odd wild value these
    ADCs produce -- a spike can't be the middle of five, so it disappears
    completely rather than being averaged in and dragging the answer with it.

    Nothing in SunFounder's stack does this: robot_hat reads the ADC once per
    channel and picarx passes that straight through, so every spike reaches the
    caller. Their conditioning is per-channel slope/offset calibration and
    thresholds, which is a different problem -- it corrects a sensor that reads
    consistently wrong, not one that occasionally reads nonsense.

    A median survives fewer than half the readings being wild, and not one more.
    If a sensor is wrong more often than it is right, no amount of smoothing will
    help and the sensor or its wiring needs looking at.

    The readings are taken back to back, not spread over time: three I2C reads
    take microseconds, so all of them describe the same instant and nothing has to
    wait. Smoothing costs nothing a moving robot would notice.
    """
    samples = _sample_line(car, smooth)
    return {key: values[len(values) // 2] for key, values in samples.items()}


def read_line_noise(car, smooth=5):
    """(medians, spreads) -- how steady each sensor is being.

    `spreads` is max minus min across the readings for that sensor, so a big
    number means that sensor is jumping around. Used by the cockpit's live view so
    noise is something you can see rather than something you infer from a number
    that won't sit still.
    """
    samples = _sample_line(car, smooth)
    medians = {key: values[len(values) // 2] for key, values in samples.items()}
    spreads = {key: values[-1] - values[0] for key, values in samples.items()}
    return medians, spreads


def read_distance_once(car):
    """One raw ultrasonic reading in centimetres. Raises NoSensor if unfitted.

    A reading of 0 or less means no echo came back, which is a valid answer.
    """
    for name in ("get_distance", "ultrasonic"):
        target = getattr(car, name, None)
        if target is None:
            continue
        value = target() if callable(target) else target.read()
        if value is None:
            raise NoSensor("this robot has no ultrasonic sensor fitted")
        return float(value)
    raise NoSensor("this robot has no ultrasonic sensor fitted")


class Distance:
    """Ultrasonic readings, medianed over time instead of over a pause.

    Call read() as often as you like. It pings when the sensor is ready and
    returns immediately either way, so the median builds up across calls rather
    than inside one -- which is what lets a steering loop check the distance
    without the robot driving blind while it waits.
    """

    def __init__(self, samples=PING_SAMPLES, spacing=PING_SPACING,
                 memory=PING_MEMORY):
        self.samples = max(1, int(samples))
        self.spacing = float(spacing)
        self.memory = float(memory)
        self._history = []          # (timestamp, centimetres), oldest first
        self._last_ping_at = 0.0

    def read(self, car, samples=None):
        """Returns (distance, used, spread).

        distance -- median of the recent readings, or -1.0 when nothing is in
                    range
        used     -- how many readings that median came from
        spread   -- max minus min of them, i.e. how much the sensor disagreed
                    with itself. Small means trust it.
        """
        keep = max(1, int(samples if samples is not None else self.samples))
        now = time.monotonic()

        if now - self._last_ping_at >= self.spacing:
            self._last_ping_at = now
            reading = read_distance_once(car)
            # The ping happened either way, so the timer above is right to have
            # moved; there's just no distance to remember from a missed echo.
            if reading > 0:
                self._history.append((now, reading))

        # Rebuilt rather than trimmed with a del-slice: `del h[:len(h) - keep]`
        # looks equivalent but goes negative while fewer than `keep` readings
        # exist, which quietly keeps only the newest -- and then the "median" is
        # one reading and any outlier wins.
        self._history[:] = [
            (stamp, value) for stamp, value in self._history
            if now - stamp <= self.memory
        ][-keep:]

        if not self._history:
            return -1.0, 0, 0.0

        values = sorted(value for _, value in self._history)
        median = values[len(values) // 2]
        return round(median, 1), len(values), round(values[-1] - values[0], 1)


def check_line_sensors(read, ask=None, show=None):
    """Walk someone through checking L, C and R aren't mislabelled.

    `read` is called to get a {'L','C','R'} dict, `ask` to wait for the student
    and `show` to talk to them -- so the cockpit and a plain script can share this
    without either dictating how it looks.

    ask and show default to input and print, but are looked up when called rather
    than captured here: a default of `ask=input` would bind whatever `input` was at
    import time, and quietly ignore anything that replaced it afterwards.

    Returns True if all three matched.
    """
    ask = ask if ask is not None else input
    show = show if show is not None else print

    names = {"L": "left", "C": "centre", "R": "right"}
    good = True

    show("Checking the line sensors. Keep the robot still.")
    show("Cover one sensor at a time with a finger or something dark.\n")

    for expected in LINE_KEYS:
        ask(f"  Cover the {names[expected].upper()} sensor, then press Enter ... ")
        sensors = read()

        # Lower is darker, so the covered one should be the smallest reading.
        darkest = min(LINE_KEYS, key=lambda key: sensors[key])

        if darkest == expected:
            show(f"    saw {names[expected]:6}  {sensors}  ok\n")
        else:
            good = False
            show(f"    saw {names[darkest]} instead of {names[expected]}"
                 f"   {sensors}")
            show("    ^ these two are the other way round\n")

    if good:
        show("All three match: L, C and R are correct.")
    else:
        show("The sensors don't match their names, so the readings are")
        show("mislabelled and anything you steer from them is mirrored.")
        show("Worth reporting before the robot is used.")
    return good

"""Turning a student's speed number into motor PWM. Shared by roboshine and the
cockpit.

Why this exists, and why it doesn't just call picarx's set_motor_speed():

    if speed != 0:
        speed = int(speed / 2) + 50      # picarx/picarx.py, v2.0

picarx maps *any* non-zero speed onto 50-100% PWM duty, so its slowest possible
speed is half power -- which on a geared 8.4V robot is a good deal faster than a
15-year-old wants for a first drive, and there is no input that produces less.
Nothing in the 1-100 range picarx advertises is actually slow.

So the duty is set directly here instead: direction pin, then pulse_width_percent.
That's the same pair of operations picarx performs, minus the +50 floor, and it
gives the whole span between "just barely turning" and "flat out" instead of only
the top half of it.

Speeds are 0-1000 rather than 0-100 for the same reason. Once the bottom of the
range is genuinely slow, 100 steps is coarse: the difference between 1 and 2 would
be a visible jump. 1000 steps makes "a bit slower" expressible.

If a picarx without the expected internals turns up, this falls back to
set_motor_speed() and says so once -- driving coarsely beats not driving.
"""

SPEED_MAX = 1000

# Below roughly this duty a geared DC motor hums and heats without turning, and
# the exact figure depends on the gearbox, the floor and how charged the battery
# is. Speed 1 maps here, so this is what "as slow as it goes" means -- if the
# robots turn out to need more, raise it (or set "min_duty" in ~/.roboshine.json)
# rather than teaching students that low numbers do nothing.
DEFAULT_MIN_DUTY = 25.0
MAX_DUTY = 100.0

_warned = False


def min_duty(settings=None):
    """The duty speed 1 maps to. Overridable per robot, since motors vary."""
    if settings is None:
        from . import _config
        settings = _config.load()
    try:
        value = float(settings.get("min_duty", DEFAULT_MIN_DUTY))
    except (TypeError, ValueError):
        return DEFAULT_MIN_DUTY
    # A floor above the ceiling, or a negative one, would make every speed
    # meaningless; ignore rather than obey.
    return value if 0 <= value < MAX_DUTY else DEFAULT_MIN_DUTY


def duty_for(speed, floor=None):
    """A speed of 0..SPEED_MAX as a PWM duty percentage.

    0 stops. 1 is the slowest the motor will actually turn, SPEED_MAX is full
    power, and everything between is a straight line -- so doubling the number
    doesn't double the speed, but bigger is always faster.
    """
    speed = abs(float(speed))
    if speed == 0:
        return 0.0
    if floor is None:
        floor = min_duty()
    fraction = min(speed, SPEED_MAX) / SPEED_MAX
    return floor + fraction * (MAX_DUTY - floor)


def _has_low_level(car):
    return all(hasattr(car, name) for name in
               ("motor_direction_pins", "motor_speed_pins"))


def _wheel(car, index, signed_speed, floor):
    """One motor, by its picarx index (0 or 1), signed in picarx's own terms."""
    duty = duty_for(signed_speed, floor)

    # Respect picarx's own per-motor direction calibration if it has one, so a
    # robot someone has calibrated through picarx still drives the way it did.
    calibration = 1
    values = getattr(car, "cali_dir_value", None)
    if isinstance(values, (list, tuple)) and len(values) > index:
        try:
            calibration = int(values[index]) or 1
        except (TypeError, ValueError):
            calibration = 1

    direction = calibration if signed_speed >= 0 else -calibration

    if direction < 0:
        car.motor_direction_pins[index].high()
    else:
        car.motor_direction_pins[index].low()
    car.motor_speed_pins[index].pulse_width_percent(duty)


def drive(car, left, right, flipped=False):
    """Drive the two wheels. `left` and `right` are -SPEED_MAX..SPEED_MAX, with
    positive meaning that wheel goes *forwards*.

    Returns immediately; the motors keep running until something stops them.
    """
    global _warned

    if flipped:
        left, right = -left, -right

    if not _has_low_level(car):
        if not _warned:
            _warned = True
            print("roboshine: this picarx has no direct PWM access, so slow "
                  "speeds will be limited")

        # Coarse but driving. picarx's own scale is 0-100 and floors at half
        # power, so nothing here can crawl -- but a robot that drives too fast
        # beats a robot that raises an exception in front of a class.
        setter = getattr(car, "set_motor_speed", None)
        if setter is not None:
            setter(1, int(left / SPEED_MAX * 100))
            setter(2, int(-right / SPEED_MAX * 100))
            return

        # Older still: only forward()/backward(), which means no per-wheel
        # control either. Drive both wheels at whichever speed is larger.
        speed = int(max(abs(left), abs(right)) / SPEED_MAX * 100)
        backwards = (left + right) < 0
        if hasattr(car, "forward") and hasattr(car, "backward"):
            car.backward(speed) if backwards else car.forward(speed)
            return

        raise RuntimeError("this robot's library can't drive the motors")

    floor = min_duty()
    # Motor 2 is mounted mirror-image to motor 1 -- picarx's own forward() sends
    # it the opposite sign to go straight ahead. Undoing that here means every
    # caller above can talk about wheels rather than about motor orientation.
    _wheel(car, 0, left, floor)
    _wheel(car, 1, -right, floor)

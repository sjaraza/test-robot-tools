"""roboshine -- simple robot commands for your own Python scripts.

Runs on the robot. Put this at the top of your script:

    import roboshine as robot

    robot.drive('f', 20, seconds=2)
    print(robot.get_distance_cm())
    robot.stop()

Type robot.showHelp() to see everything available.

Notes for anyone reading the code rather than using it:

* The hardware is opened lazily, on the first command that needs it. So
  showHelp() works on a machine with no robot attached, and importing this
  module can't fail because a servo is unplugged.
* The motors are stopped automatically when your script ends, however it ends --
  including a crash or Ctrl-C. A student's script exiting with the robot still
  driving is how robots end up under furniture.
"""

import atexit
import time

__version__ = "0.1"

__all__ = [
    "drive", "stop", "steer", "get_distance_cm", "wait", "showHelp",
]

# picarx steering limit, degrees either side of straight.
MAX_STEER = 30

# An HC-SR04-style sensor needs roughly 60ms of quiet between pings. Fire faster
# and the echo from the previous ping arrives inside the next measurement window,
# which reads as wildly wrong distances rather than as noise.
PING_SPACING = 0.06
PING_SAMPLES = 3

# 'f' is what students will type; the long names are here so that both work.
FORWARD = ("f", "fwd", "forward")
BACKWARD = ("b", "back", "backward", "backwards", "reverse")
LEFT = ("l", "left")
RIGHT = ("r", "right")

_car = None


def _hardware():
    """The Picarx object, created on first use."""
    global _car
    if _car is not None:
        return _car

    try:
        from picarx import Picarx
    except ImportError as exc:
        raise RuntimeError(
            f"the picarx library isn't installed ({exc}).\n"
            "Run: bash ~/test-robot-tools/setup-picarx.sh"
        ) from exc

    try:
        _car = Picarx()
    except PermissionError as exc:
        # picarx writes its servo calibration to a hardcoded /opt/picar-x. On a
        # fresh system that directory doesn't exist and /opt is root-owned, so
        # this fails with errno 13 on a path that isn't even there.
        path = getattr(exc, "filename", None) or "/opt/picar-x"
        raise RuntimeError(
            f"no permission to write {path}. Fix it once:\n"
            f"    sudo mkdir -p {path}\n"
            f"    sudo chown -R $USER:$USER {path}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"the robot hardware didn't respond ({type(exc).__name__}: {exc}).\n"
            "Check the battery switch is on and the robot-hat is seated."
        ) from exc

    return _car


def _stop_on_exit():
    """Never leave the motors running when a script ends."""
    if _car is None:
        return                      # hardware was never touched
    try:
        _car.stop()
        _car.set_dir_servo_angle(0)
    except Exception:
        pass                        # exiting anyway; nothing useful to say


atexit.register(_stop_on_exit)


def _check_speed(speed):
    if not isinstance(speed, (int, float)):
        raise TypeError(f"speed should be a number, not {type(speed).__name__}")
    if not 0 <= speed <= 100:
        raise ValueError(f"speed should be between 0 and 100, not {speed}")
    return int(speed)


def drive(direction, speed=10, seconds=None):
    """Drive the robot.

        drive('f')                  forward at the default gentle speed
        drive('b', 30)              backward, a bit quicker
        drive('l', 20, seconds=2)   curve left for two seconds, then stop
        drive('r', 20)              curve right, keeps going until you stop()

    direction : 'f' forward, 'b' backward, 'l' left, 'r' right
    speed     : 0 to 100. Starts at 10, which is slow enough to watch.
    seconds   : optional. If given, the robot stops itself afterwards.

    'l' and 'r' turn the front wheels and drive forward -- this robot steers
    like a car, so it can't spin on the spot.
    """
    # Check everything the student passed in BEFORE touching the hardware.
    # Two reasons: a typo should say what the typo was rather than complaining
    # about a library, and a bad `seconds` shouldn't be discovered after the
    # robot has already started moving.
    speed = _check_speed(speed)

    if not isinstance(direction, str):
        raise TypeError("direction should be a string like 'f' or 'forward'")

    key = direction.strip().lower()
    if key not in FORWARD + BACKWARD + LEFT + RIGHT:
        raise ValueError(
            f"'{direction}' isn't a direction I know.\n"
            "Use 'f' forward, 'b' backward, 'l' left, or 'r' right."
        )

    if seconds is not None and (not isinstance(seconds, (int, float))
                                or isinstance(seconds, bool) or seconds < 0):
        raise ValueError(f"seconds should be a positive number, not {seconds!r}")

    car = _hardware()

    if key in FORWARD:
        car.set_dir_servo_angle(0)
        car.forward(speed)
    elif key in BACKWARD:
        car.set_dir_servo_angle(0)
        car.backward(speed)
    elif key in LEFT:
        car.set_dir_servo_angle(-MAX_STEER)
        car.forward(speed)
    else:                                   # RIGHT, the only case left
        car.set_dir_servo_angle(MAX_STEER)
        car.forward(speed)

    if seconds is not None:
        try:
            time.sleep(seconds)
        finally:
            # Stop even if the student interrupts the wait with Ctrl-C.
            stop()


def stop():
    """Stop the motors and straighten the front wheels."""
    car = _hardware()
    car.stop()
    car.set_dir_servo_angle(0)


def steer(angle):
    """Point the front wheels without driving.

        steer(-20)   turn them left
        steer(0)     straighten up
        steer(15)    turn them right

    angle : -30 (full left) to 30 (full right).
    """
    if not isinstance(angle, (int, float)):
        raise TypeError(f"angle should be a number, not {type(angle).__name__}")
    if not -MAX_STEER <= angle <= MAX_STEER:
        raise ValueError(
            f"angle should be between {-MAX_STEER} and {MAX_STEER}, not {angle}")
    _hardware().set_dir_servo_angle(int(angle))


def get_distance_cm(samples=PING_SAMPLES):
    """How far away is the thing in front? Distance in centimetres.

    Returns -1 when nothing is close enough to bounce the sound back.

        space = get_distance_cm()
        if space > 0 and space < 20:
            stop()

    Takes the middle of three readings, spaced out slightly. One reading on its
    own is often wrong: sound bounces off more than you'd think.
    """
    car = _hardware()

    readings = []
    for _ in range(max(1, int(samples))):
        time.sleep(PING_SPACING)

        value = None
        for name in ("get_distance", "ultrasonic"):
            target = getattr(car, name, None)
            if target is None:
                continue
            value = target() if callable(target) else target.read()
            break

        if value is None:
            raise RuntimeError("this robot has no ultrasonic sensor fitted")
        if value > 0:
            readings.append(float(value))

    if not readings:
        return -1.0

    readings.sort()
    return round(readings[len(readings) // 2], 1)


def wait(seconds):
    """Do nothing for a while. The robot keeps doing whatever it was doing.

        drive('f', 20)
        wait(1.5)
        stop()
    """
    if not isinstance(seconds, (int, float)) or seconds < 0:
        raise ValueError(f"seconds should be a positive number, not {seconds}")
    time.sleep(seconds)


def showHelp():
    """Print every command in this library."""
    print(f"""
roboshine {__version__} -- robot commands you can use in your own scripts

  drive(direction, speed=10, seconds=None)
      Drive the robot.
        drive('f')                 forward, gently
        drive('b', 30)             backward at speed 30
        drive('l', 20, seconds=2)  curve left for 2 seconds, then stop
      direction : 'f' forward, 'b' backward, 'l' left, 'r' right
      speed     : 0 to 100
      seconds   : optional; the robot stops itself when the time is up

  stop()
      Stop the motors and straighten the wheels.

  steer(angle)
      Point the front wheels without driving. -30 is full left, 30 full right.

  get_distance_cm()
      How far away the thing in front is, in centimetres.
      Returns -1 if nothing is close enough to detect.

  wait(seconds)
      Pause your script. The robot carries on doing what it was doing.

  showHelp()
      Print this.

A whole script looks like this:

  import roboshine as robot

  robot.drive('f', 20, seconds=1)
  if robot.get_distance_cm() < 20:
      robot.drive('b', 20, seconds=1)
  robot.stop()

The motors always stop when your script finishes, even if it crashes.
""")

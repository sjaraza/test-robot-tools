"""roboshine -- simple robot commands for your own Python scripts.

Runs on the robot. Put this at the top of your script:

    import roboshine as robot

    robot.steerLeft(20)
    robot.driveForward(20)
    robot.wait(2)
    robot.stop()

Type robot.showHelp() to see everything available.

Notes for anyone reading the code rather than using it:

* Left/right and up/down are separate for the camera too, so lookLeft(40) then
  lookUp(20) leaves the camera pointing up and to the left. lookStraight()
  resets both.
* Driving and steering are separate on purpose. driveForward() does not touch
  the steering, so steerLeft() then driveForward() curves left -- if driving
  straightened the wheels, the steer command would silently be undone.
* Every command returns immediately. driveForward() sets the motors going and
  hands control straight back, so the robot keeps driving until stop() is
  called. That means a script can watch a sensor while moving. wait() is the
  only command that pauses, which keeps it obvious where the pauses are.
* The hardware is opened lazily, on the first command that needs it. So
  showHelp() works on a machine with no robot attached, and importing this
  module can't fail because a servo is unplugged.
* The motors are stopped automatically when your script ends, however it ends --
  including a crash or Ctrl-C. A student's script exiting with the robot still
  driving is how robots end up under furniture.
"""

import atexit
import time

__version__ = "0.5"

__all__ = [
    "driveForward", "driveBack", "stop",
    "steerLeft", "steerRight", "steerStraight",
    "lookLeft", "lookRight", "lookUp", "lookDown", "lookStraight",
    "get_distance_cm", "get_line_sensors", "get_line_position",
    "wait", "showHelp",
]

# picarx steering limit, degrees either side of straight.
MAX_STEER = 30

# Camera limits. Tilt is deliberately asymmetric -- the mount can look further up
# than down, and pretending otherwise would just make lookDown(60) fail oddly.
MAX_PAN = 90
MAX_TILT_UP = 65
MAX_TILT_DOWN = 35

# An HC-SR04-style sensor needs roughly 60ms of quiet between pings. Fire faster
# and the echo from the previous ping arrives inside the next measurement window,
# which reads as wildly wrong distances rather than as noise.
PING_SPACING = 0.06
PING_SAMPLES = 3

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


def _check_number(value, name, low, high):
    """Validate before any hardware is touched.

    Two reasons for checking first: a typo should say what the typo was rather
    than complaining about a library, and a bad number shouldn't be discovered
    after the robot has already started moving.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} should be a number, not {type(value).__name__}")
    if not low <= value <= high:
        raise ValueError(f"{name} should be between {low} and {high}, not {value}")
    return value


def _run(backward, speed):
    """Shared body of driveForward and driveBack."""
    speed = int(_check_number(speed, "speed", 0, 100))
    car = _hardware()
    # Deliberately does not touch the steering: whatever steerLeft/steerRight
    # last set stays set, so the two commands compose.
    #
    # The calls look inverted because they are: on these robots picarx's
    # forward() drives the car backwards. The names students see describe what
    # the car really does, and this line is the only place that is untangled.
    car.forward(speed) if backward else car.backward(speed)


def driveForward(speed=10):
    """Start driving forwards, and keep going until stop() is called.

        driveForward()      gently
        driveForward(30)    quicker

    speed : 0 to 100. Starts at 10, slow enough to watch.

    Returns straight away -- the robot carries on while your script does other
    things, so you can watch a sensor while moving:

        driveForward(20)
        while get_distance_cm() > 20:
            wait(0.1)
        stop()

    The front wheels stay wherever you last pointed them, so this curves if you
    have steered.
    """
    _run(False, speed)


def driveBack(speed=10):
    """Start driving backwards, and keep going until stop() is called.

        driveBack(20)
        wait(1)
        stop()
    """
    _run(True, speed)


def stop():
    """Stop the motors.

    The front wheels stay where they are -- use steerStraight() to centre them.
    """
    _hardware().stop()


def steerLeft(degrees=MAX_STEER):
    """Point the front wheels left. Doesn't drive.

        steerLeft()      full left
        steerLeft(15)    half left

    degrees : 0 to 30, how far to turn. 30 is as far as the wheels go.
    """
    _check_number(degrees, "degrees", 0, MAX_STEER)
    _hardware().set_dir_servo_angle(-int(degrees))


def steerRight(degrees=MAX_STEER):
    """Point the front wheels right. Doesn't drive.

        steerRight()     full right
        steerRight(15)   half right

    degrees : 0 to 30, how far to turn. 30 is as far as the wheels go.
    """
    _check_number(degrees, "degrees", 0, MAX_STEER)
    _hardware().set_dir_servo_angle(int(degrees))


def steerStraight():
    """Point the front wheels straight ahead."""
    _hardware().set_dir_servo_angle(0)


def lookLeft(degrees=MAX_PAN):
    """Turn the camera left. Doesn't move the robot.

        lookLeft()       all the way left
        lookLeft(30)     part way

    degrees : 0 to 90.
    """
    _check_number(degrees, "degrees", 0, MAX_PAN)
    _hardware().set_cam_pan_angle(-int(degrees))


def lookRight(degrees=MAX_PAN):
    """Turn the camera right. 0 to 90 degrees."""
    _check_number(degrees, "degrees", 0, MAX_PAN)
    _hardware().set_cam_pan_angle(int(degrees))


def lookUp(degrees=MAX_TILT_UP):
    """Tilt the camera up. 0 to 65 degrees."""
    _check_number(degrees, "degrees", 0, MAX_TILT_UP)
    _hardware().set_cam_tilt_angle(int(degrees))


def lookDown(degrees=MAX_TILT_DOWN):
    """Tilt the camera down. 0 to 35 degrees -- it can't look as far down as up."""
    _check_number(degrees, "degrees", 0, MAX_TILT_DOWN)
    _hardware().set_cam_tilt_angle(-int(degrees))


def lookStraight():
    """Point the camera straight ahead, level."""
    car = _hardware()
    car.set_cam_pan_angle(0)
    car.set_cam_tilt_angle(0)


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


# How different the three readings must be before we'll say the line is under one
# of them. Relative rather than an absolute brightness threshold, so it works on a
# dark floor or a light one without calibration.
LINE_MARGIN = 50


def get_line_sensors():
    """The three line sensors under the front of the robot.

    Returns (left, middle, right) as numbers. Lower means darker, so a black line
    on a white floor reads *lower* than the floor around it.

        left, middle, right = get_line_sensors()
        print(left, middle, right)

    Numbers depend on your floor and the lighting, so print them and look before
    writing rules about them.
    """
    car = _hardware()
    reader = getattr(car, "get_grayscale_data", None)
    if reader is None:
        raise RuntimeError("this robot has no line sensors fitted")

    values = reader()
    if not values or len(values) < 3:
        raise RuntimeError(f"expected three sensor readings, got {values!r}")
    return tuple(int(v) for v in values[:3])


def get_line_position(margin=LINE_MARGIN):
    """Which sensor can see the line: 'left', 'centre', 'right', or 'lost'.

        while True:
            where = get_line_position()
            if where == 'left':
                steerLeft(15)
            elif where == 'right':
                steerRight(15)
            else:
                steerStraight()

    'lost' means all three sensors read about the same -- either the line isn't
    under the robot at all, or all three are sitting on it.

    Works out which sensor is darkest rather than comparing against a fixed
    brightness, so it doesn't need calibrating for your floor. If the three
    readings are within `margin` of each other it reports 'lost' instead of
    guessing.
    """
    left, middle, right = get_line_sensors()
    readings = (left, middle, right)

    if max(readings) - min(readings) < margin:
        return "lost"

    darkest = readings.index(min(readings))
    return ("left", "centre", "right")[darkest]


def wait(seconds):
    """Do nothing for a while. The robot keeps doing whatever it was doing.

        driveForward(20)
        wait(1.5)
        stop()
    """
    _check_number(seconds, "seconds", 0, 3600)
    time.sleep(seconds)


def showHelp():
    """Print every command in this library."""
    print(f"""
roboshine {__version__} -- robot commands you can use in your own scripts

  DRIVING
    driveForward(speed=10)
    driveBack(speed=10)
        speed : 0 to 100
        These start the motors and return immediately. The robot keeps going
        until you call stop().
        Examples:
          driveForward()      gently
          driveForward(30)    quicker

    stop()
        Stop the motors. The wheels stay pointed where they were.

  STEERING
    steerLeft(degrees=30)     point the front wheels left
    steerRight(degrees=30)    point the front wheels right
    steerStraight()           point them straight ahead
        degrees : 0 to 30. Steering does not drive; combine the two.

  CAMERA
    lookLeft(degrees=90)      turn the camera left
    lookRight(degrees=90)     turn it right
    lookUp(degrees=65)        tilt it up
    lookDown(degrees=35)      tilt it down (it can't look as far down as up)
    lookStraight()            straight ahead and level
        Left/right and up/down are separate, so they combine:
          lookLeft(40)
          lookUp(20)          now pointing up and to the left

  SENSING
    get_distance_cm()
        Centimetres to the thing in front. -1 means nothing is in range.

    get_line_sensors()
        The three sensors underneath, as (left, middle, right).
        Lower numbers are darker, so a black line reads lower than the floor.

    get_line_position()
        Which sensor sees the line: 'left', 'centre', 'right' or 'lost'.
        Example:
          where = get_line_position()
          if where == 'left':  steerLeft(15)

  OTHER
    wait(seconds)     pause your script; the robot carries on
    showHelp()        print this

A whole script looks like this:

  import roboshine as robot

  robot.steerLeft(20)
  robot.driveForward(20)     # starts moving, curving left
  robot.wait(2)              # ...for two seconds
  robot.stop()

  robot.steerStraight()
  robot.driveForward(20)
  while robot.get_distance_cm() > 20:    # drive until something is close
      robot.wait(0.1)
  robot.stop()

Driving and steering are separate, so driveForward() keeps whatever steering you
set. Commands return immediately; wait() is the only one that pauses. The motors
always stop when your script finishes, even if it crashes.
""")

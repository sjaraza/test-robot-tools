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
* steerLeft/steerRight/steerStraight all go through steer(), which is also what
  records the angle for get_steer_angle(). Anything new that moves the steering
  should call steer() rather than the servo directly, or that record goes stale.
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

__version__ = "0.7"

__all__ = [
    "driveForward", "driveBack", "stop",
    "steer", "steerLeft", "steerRight", "steerStraight", "get_steer_angle",
    "lookLeft", "lookRight", "lookUp", "lookDown", "lookStraight",
    "get_distance_cm",
    "get_line_sensors", "get_line", "checkLineSensors",
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

# The steering angle roboshine last asked for. The picar-x servo can't be read
# back, so this is the only way get_steer_angle() can answer at all.
_steer_angle = 0


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


def steer(angle):
    """Point the front wheels at an exact angle. Negative is left, positive right.

        steer(0)        straight ahead
        steer(-20)      20 degrees left
        steer(12)       12 degrees right

    angle : -30 to 30.

    This is the one to use when the number comes from a calculation rather than
    from you -- following a line, say, where how hard to steer depends on how far
    off the line the robot is:

        turn = get_line(25)                  # -30 to 30, or None if it can't tell
        if turn is not None:
            steer(turn)

    steerLeft() and steerRight() are this with the sign built in.
    """
    global _steer_angle
    _check_number(angle, "angle", -MAX_STEER, MAX_STEER)
    _hardware().set_dir_servo_angle(int(angle))
    _steer_angle = int(angle)


def get_steer_angle():
    """The angle the front wheels are pointing: -30 (left) to 30 (right).

    This is what roboshine last asked for, not a reading from the servo -- the
    picar-x can't report where its wheels actually are. It starts at 0, so a
    script that steers only through this library gets a truthful answer.

    Handy for changing the steering gradually, which wobbles far less than
    jumping straight to a new angle:

        steer(get_steer_angle() * 0.7 + wanted * 0.3)
    """
    return _steer_angle


def steerLeft(degrees=MAX_STEER):
    """Point the front wheels left. Doesn't drive.

        steerLeft()      full left
        steerLeft(15)    half left

    degrees : 0 to 30, how far to turn. 30 is as far as the wheels go.
    """
    _check_number(degrees, "degrees", 0, MAX_STEER)
    steer(-int(degrees))


def steerRight(degrees=MAX_STEER):
    """Point the front wheels right. Doesn't drive.

        steerRight()     full right
        steerRight(15)   half right

    degrees : 0 to 30, how far to turn. 30 is as far as the wheels go.
    """
    _check_number(degrees, "degrees", 0, MAX_STEER)
    steer(int(degrees))


def steerStraight():
    """Point the front wheels straight ahead."""
    steer(0)


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

    Returns a dict with the left, centre and right readings:

        sensors = get_line_sensors()
        print(sensors)                      # {'L': 812, 'C': 240, 'R': 795}
        print(sensors["C"])                 # just the middle one

    Lower numbers are darker, so a black line on a pale floor reads *lower* than
    the floor around it. The actual numbers depend on your floor and the lighting,
    so print them and look before writing rules about them.

    The keys are the same L, C and R printed above the readings in the cockpit
    (item 6), and naming them this way means you never have to remember which
    order the three came in.
    """
    car = _hardware()
    reader = getattr(car, "get_grayscale_data", None)
    if reader is None:
        raise RuntimeError("this robot has no line sensors fitted")

    values = reader()
    if not values or len(values) < 3:
        raise RuntimeError(f"expected three sensor readings, got {values!r}")

    left, centre, right = (int(v) for v in values[:3])
    return {"L": left, "C": centre, "R": right}


def get_line(gain=1, margin=LINE_MARGIN):
    """Where the line is: negative if it is off to the left, positive to the right.

        turn = get_line(25)
        if turn is not None:
            steer(turn)                     # follow the line
        else:
            stop()                          # can't see it any more

    With no `gain` the answer runs from -1 (line hard left) through 0 (line under
    the middle sensor) to +1 (line hard right). Give a gain and it is multiplied
    by it, so `get_line(25)` hands back a number you can pass straight to
    steer() -- bigger gain means sharper corrections.

    Returns **None** when the three sensors read too much alike to tell where the
    line is: either it isn't under the robot at all, or all three are sitting on
    it. Always check for None before using the number; treating it as 0 would
    drive the robot confidently off the track.

    gain   : 0 to 100. Not an angle -- it's how much steering you get per unit of
             error, so a big gain means the wheels go to full lock while the line
             is still only halfway across the sensors. The answer is kept inside
             the wheels' -30 to 30 limit, so a gain that's too big simply stops
             helping rather than making steer() complain.
    margin : how different the readings must be before it will answer at all.
             The default suits most floors; raise it if you get numbers when the
             robot is clearly lost, lower it if you get None when it isn't.

    Worked out from how dark each sensor is compared with the brightest of the
    three, so there is nothing to calibrate for a particular floor or room.
    """
    _check_number(gain, "gain", 0, 100)
    _check_number(margin, "margin", 0, 4096)

    sensors = get_line_sensors()
    readings = (sensors["L"], sensors["C"], sensors["R"])

    if max(readings) - min(readings) < margin:
        return None                     # all three agree; nothing to steer by

    # Lower is darker, so "how dark" is the distance below the brightest reading.
    # The brightest sensor scores 0 and drops out, which is what makes the sum
    # below behave.
    brightest = max(readings)
    weights = [brightest - value for value in readings]
    total = sum(weights)
    if total == 0:
        return None

    # -1 for the left sensor, 0 for the middle, +1 for the right.
    position = (-weights[0] + weights[2]) / total
    answer = position * gain

    # Clamped so that get_line(40) can't produce an angle steer() would refuse.
    answer = max(-MAX_STEER, min(MAX_STEER, answer))
    return round(answer, 2)


def checkLineSensors():
    """Check the three sensors are the way round roboshine thinks they are.

        checkLineSensors()

    Asks you to cover one sensor at a time and reports what it saw. Worth two
    minutes on a robot you haven't used before: if left and right are swapped,
    a line follower steers the wrong way and wobbles harder the more it corrects,
    which looks exactly like badly chosen numbers rather than a wiring surprise.

    Returns True if all three matched, False otherwise.
    """
    keys = ("L", "C", "R")
    names = {"L": "left", "C": "centre", "R": "right"}
    good = True

    print("Checking the line sensors. Keep the robot still.")
    print("Cover one sensor at a time with a finger or something dark.\n")

    for expected in keys:
        input(f"  Cover the {names[expected].upper()} sensor, then press Enter ... ")
        sensors = get_line_sensors()

        # Lower is darker, so the covered sensor should be the smallest reading.
        darkest = min(keys, key=lambda key: sensors[key])

        if darkest == expected:
            print(f"    saw {names[expected]:6}  {sensors}  ok\n")
        else:
            good = False
            print(f"    saw {names[darkest]} instead of {names[expected]}"
                  f"   {sensors}")
            print("    ^ these two are the other way round\n")

    if good:
        print("All three match: L, C and R are correct.")
    else:
        print("The sensors don't match their names, so get_line_sensors() has")
        print("them mislabelled and get_line() will steer the wrong way.")
        print("Worth reporting before the robot is used.")
    return good


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

    steer(angle)              exact angle: -30 is full left, 30 full right
        For angles you calculate rather than type:
          steer(get_line(25))
    get_steer_angle()         the angle the wheels are pointing now

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
        The three sensors underneath, as {{'L': .., 'C': .., 'R': ..}}.
        Lower numbers are darker, so a black line reads lower than the floor.
          sensors = get_line_sensors()
          print(sensors["C"])          just the middle one

    get_line(gain=1)
        Where the line is: negative means it's off to the left, positive means
        right, 0 means dead centre. None when the sensors can't tell.
        With a gain, the answer is ready to steer with:
          turn = get_line(25)
          if turn is not None:  steer(turn)
          else:                 stop()
        A bigger gain corrects harder. Never goes outside -30 to 30.

    checkLineSensors()
        Check L and R aren't the other way round. Worth doing once on a robot
        you haven't used before.

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

Following a line is the same shape, steering by how far off it is:

  robot.driveForward(15)
  while True:
      turn = robot.get_line(25)          # -30 to 30, or None if it can't tell
      if turn is None:
          robot.stop()
          break
      robot.steer(turn)                  # bigger gain = sharper corrections
      robot.wait(0.05)

Driving and steering are separate, so driveForward() keeps whatever steering you
set. Commands return immediately; wait() is the only one that pauses. The motors
always stop when your script finishes, even if it crashes.
""")

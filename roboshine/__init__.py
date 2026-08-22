"""roboshine -- simple robot commands for your own Python scripts.

Runs on the robot. Put this at the top of your script:

    import time
    import roboshine as robot

    robot.steerLeft(20)
    robot.driveForward(20)
    time.sleep(2)
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
* Nothing in here pauses. Every command returns immediately: driveForward()
  sets the motors going and hands control straight back, so the robot keeps
  driving until stop() is called, and a script can watch a sensor while moving.
  Pausing is time.sleep()'s job, which keeps the pauses in the student's script
  where they can see them. (checkLineSensors() is the one exception, and only
  because it waits for you to press Enter.)
* The sensor readers never pause either, which is the whole point of them. An
  ultrasonic sensor needs quiet between pings, so get_distance_cm() skips the
  ping when it's called too soon and hands back what it already knows, rather
  than sleeping until the sensor is ready -- a sleep there would leave the robot
  driving blind inside somebody's steering loop. (checkLineSensors() is the one
  exception, and only because it waits for you to press Enter.)
* The sensors hand back numbers, not decisions. read_line_sensors() gives the
  three readings and stops there: working out what they mean is the interesting
  part, and doing it for students would take the lesson away.
* The hardware is opened lazily, on the first command that needs it. So
  showHelp() works on a machine with no robot attached, and importing this
  module can't fail because a servo is unplugged.
* The motors are stopped automatically when your script ends, however it ends --
  including a crash or Ctrl-C. A student's script exiting with the robot still
  driving is how robots end up under furniture.
"""

import atexit
import time

from . import _config

__version__ = "0.9"

__all__ = [
    "driveForward", "driveBack", "stop",
    "steer", "steerLeft", "steerRight", "steerStraight", "get_steer_angle",
    "lookLeft", "lookRight", "lookUp", "lookDown", "lookStraight",
    "get_distance_cm", "read_line_sensors", "checkLineSensors",
    "flipDrive", "is_drive_flipped",
    "showHelp",
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
# which reads as wildly wrong distances rather than as noise. get_distance_cm()
# honours this by *not pinging* when it's called too soon, rather than by sleeping
# -- sleeping would stall whatever loop the student wrote.
PING_SPACING = 0.06
PING_SAMPLES = 3

# How long a distance reading is worth remembering. On a moving robot an older one
# is a measurement of somewhere else.
PING_MEMORY = 0.5

_car = None

# The steering angle roboshine last asked for. The picar-x servo can't be read
# back, so this is the only way get_steer_angle() can answer at all.
_steer_angle = 0

# Recent distance readings as (timestamp, centimetres), oldest first, and when the
# sensor was last pinged. Kept here so get_distance_cm() can average over a loop's
# worth of readings without ever pausing to collect them.
_ping_history = []
_last_ping_at = 0.0


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

    # Which way round the motor wires were pushed on decides whether picarx's
    # forward() actually drives this car forwards, so it's a per-robot setting
    # rather than something the library can know. flipDrive() changes it, and
    # this is the only place it is applied.
    if _config.drive_flipped():
        backward = not backward

    # Deliberately does not touch the steering: whatever steerLeft/steerRight
    # last set stays set, so the two commands compose.
    car.backward(speed) if backward else car.forward(speed)


def driveForward(speed=10):
    """Start driving forwards, and keep going until stop() is called.

        driveForward()      gently
        driveForward(30)    quicker

    speed : 0 to 100. Starts at 10, slow enough to watch.

    Returns straight away -- the robot carries on while your script does other
    things, so you can watch a sensor while moving:

        driveForward(20)
        while get_distance_cm() > 20:
            time.sleep(0.1)
        stop()

    The front wheels stay wherever you last pointed them, so this curves if you
    have steered.
    """
    _run(False, speed)


def driveBack(speed=10):
    """Start driving backwards, and keep going until stop() is called.

        driveBack(20)
        time.sleep(1)
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

        sensors = read_line_sensors()
        steer(<something you work out from those three numbers>)

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
        if 0 < space < 20:
            stop()

    Returns straight away -- it never pauses your script. That matters in a loop
    that is also steering: a pause here would leave the robot driving blind for as
    long as it lasted.

    The sensor needs about 60ms of quiet between pings, so calling this faster than
    that gives you the most recent answer again rather than a new ping. Called in a
    loop it keeps the last few readings and hands back the middle one, which is
    steadier than any single reading -- sound bounces off more than you would
    think. The first call has only one reading to go on, so give it a few times
    round the loop before trusting a surprising number.
    """
    global _last_ping_at

    car = _hardware()
    keep = max(1, int(samples))
    now = time.monotonic()

    # Only fire a fresh ping once the sensor has had its quiet time. Firing sooner
    # doesn't just waste effort: the echo from the previous ping arrives inside
    # this measurement window, which reads as a wildly wrong distance rather than
    # as noise.
    if now - _last_ping_at >= PING_SPACING:
        _last_ping_at = now

        value = None
        for name in ("get_distance", "ultrasonic"):
            target = getattr(car, name, None)
            if target is None:
                continue
            value = target() if callable(target) else target.read()
            break

        if value is None:
            raise RuntimeError("this robot has no ultrasonic sensor fitted")

        # A reading of 0 or less means no echo came back. The ping still happened,
        # so the timer above is right to have moved, but there's no distance to
        # remember.
        if value > 0:
            _ping_history.append((now, float(value)))

    # Readings go stale: on a moving robot a second-old distance is a distance
    # from somewhere else. Dropping them is also what lets -1 mean "nothing in
    # range" again once whatever was in front has gone. Keeping only the last
    # `keep` of what survives is what makes the median a median of recent pings.
    #
    # Written as one rebuild rather than a del-slice on purpose: `del
    # history[:len(history) - keep]` looks equivalent but goes negative while
    # fewer than `keep` readings have been collected, which silently throws away
    # everything except the newest -- and then the "median" is a single reading
    # and any outlier wins.
    _ping_history[:] = [
        (stamp, value) for stamp, value in _ping_history
        if now - stamp <= PING_MEMORY
    ][-keep:]

    if not _ping_history:
        return -1.0

    values = sorted(value for _, value in _ping_history)
    return round(values[len(values) // 2], 1)


# How different the three readings must be before we'll say the line is under one
# of them. Relative rather than an absolute brightness threshold, so it works on a
# dark floor or a light one without calibration.
LINE_MARGIN = 50


def read_line_sensors():
    """The three line sensors under the front of the robot.

    Returns a dict with the left, centre and right readings:

        sensors = read_line_sensors()
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


def is_drive_flipped():
    """True when this robot needs its forward and reverse swapped over.

    A setting rather than a fact about all robots: which way round the two motor
    wires were pushed on when the kit was built decides it, so it varies from
    robot to robot. flipDrive() changes it.
    """
    _config.forget()             # another process may have changed it
    return _config.drive_flipped()


def flipDrive():
    """Swap forward and reverse on this robot, and remember it.

        flipDrive()

    Run this once if driveForward() drives your robot *backwards*. The setting is
    saved in ~/.roboshine.json, so it applies to every script you write from then
    on -- your robot, not just this program. Run it again to swap back.

    The reason it's needed: the two motor wires can go on either way round, and
    nothing on the robot can tell which way they went. Your robot may well be
    wired the opposite way to the one next to it.

    Returns True if forward and reverse are now swapped.
    """
    flipped = not is_drive_flipped()
    _config.set_drive_flipped(flipped)

    if flipped:
        print("Forward and reverse are now swapped over.")
    else:
        print("Forward and reverse are back to normal.")
    print(f"Saved in {_config.CONFIG_PATH} -- every script you write will use it.")
    print("Check with a short driveForward(15) and see which way it goes.")
    return flipped


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
        sensors = read_line_sensors()

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
        print("The sensors don't match their names, so read_line_sensors() has")
        print("them mislabelled, so anything you steer from them is mirrored.")
        print("Worth reporting before the robot is used.")
    return good


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
          steer(get_steer_angle() * 0.7 + wanted * 0.3)
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
        Never pauses your script, so it's safe to call inside a driving loop.

    read_line_sensors()
        The three sensors underneath, as {{'L': .., 'C': .., 'R': ..}}.
        Lower numbers are darker, so the sensor over a black line reads lower
        than the two on the floor.
          sensors = read_line_sensors()
          print(sensors)               all three
          print(sensors["C"])          just the middle one
        What the numbers mean is up to you -- that's the interesting part.

    checkLineSensors()
        Check L and R aren't the other way round. Worth doing once on a robot
        you haven't used before. This one waits for you to press Enter.

  YOUR ROBOT
    flipDrive()
        Swap forward and reverse, if driveForward() drives yours backwards.
        The two motor wires can go on either way round and nothing can tell
        which way they went, so this varies from robot to robot. Saved for
        every script you write from now on -- the cockpit's item 11 does the
        same thing.
    is_drive_flipped()        True if they're currently swapped

  OTHER
    showHelp()        print this
        To pause, use Python's own time.sleep(seconds) -- nothing in roboshine
        pauses on its own.

A whole script looks like this:

  import time
  import roboshine as robot

  robot.steerLeft(20)
  robot.driveForward(20)     # starts moving, curving left
  time.sleep(2)              # ...for two seconds
  robot.stop()

  robot.steerStraight()
  robot.driveForward(20)
  while robot.get_distance_cm() > 20:    # drive until something is close
      time.sleep(0.1)
  robot.stop()

Reading the line sensors looks like this. What to do about the numbers is the
puzzle -- see examples/line_follow.py for one way:

  sensors = robot.read_line_sensors()
  print(sensors)                       # {{'L': 812, 'C': 240, 'R': 795}}

Driving and steering are separate, so driveForward() keeps whatever steering you
set. Nothing here pauses -- use time.sleep() for that -- and the motors always
stop when your script finishes, even if it crashes.
""")

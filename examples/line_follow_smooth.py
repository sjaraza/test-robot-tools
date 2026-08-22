#!/usr/bin/env python3
"""Follow a line smoothly, by steering as hard as the mistake is big.

Run it on the robot:

    python3 ~/test-robot-tools/examples/line_follow_smooth.py

This is line_follow.py's older brother. That one picks left, right or straight
and turns a fixed amount, which wobbles: it corrects just as hard for being
slightly off the line as for nearly losing it. This one asks *how far* off the
line it is and steers in proportion, which is how a real line follower works.

Press Ctrl-C to stop. The motors always stop when the script ends.
"""

import roboshine as robot

SPEED = 18          # can be higher than the simple follower -- it corrects better
GAIN = 25           # how hard to steer per unit of error. The number to play with
SMOOTH = 0.6        # 0 = jump straight to the new angle, 0.9 = very gentle
CHECK_EVERY = 0.05  # seconds between looks at the sensors
LOST_LIMIT = 20     # about a second of seeing nothing before giving up

print("Smooth line following. Ctrl-C to stop.")
print("Put the robot on the line before it starts moving.")
robot.wait(2)

robot.steerStraight()
robot.driveForward(SPEED)

lost_count = 0

try:
    while True:
        error = robot.get_line_error()

        if error is None:
            # None means the three sensors all read about the same, so there's
            # nothing to steer by. Hold the last angle briefly in case it's a gap
            # in the tape, rather than stopping at every join.
            lost_count += 1
            if lost_count > LOST_LIMIT:
                print("\nLost the line. Stopping.")
                break
        else:
            lost_count = 0

            # error is -1 when the line is off to the left and +1 when it's off
            # to the right, which is the same direction steer() uses -- so no
            # minus sign to get the wrong way round.
            wanted = error * GAIN

            # Mixing in the angle it is already at stops the wheels snapping to a
            # new position every twentieth of a second.
            angle = robot.get_steer_angle() * SMOOTH + wanted * (1 - SMOOTH)

            # steer() refuses anything past the wheels' limit, so keep it inside.
            angle = max(-30, min(30, angle))
            robot.steer(angle)

            print(f"error {error:+5.2f}   steer {angle:+6.1f}°", end="\r")

        robot.wait(CHECK_EVERY)

except KeyboardInterrupt:
    print("\nStopped by you.")

robot.stop()
robot.steerStraight()

# Things to try:
#   * raise GAIN until it starts wobbling, then back off a little -- that's
#     roughly as fast as it can correct on your floor
#   * lower SMOOTH to 0 and watch the difference the smoothing makes
#   * raise SPEED once the steering looks steady
#   * spot a junction rather than calling it lost:
#       left, middle, right = robot.get_line_dark()
#       if left and middle and right: print("junction!")
#     (run robot.calibrate_line() once at the top for that to work properly)
#   * print(robot.get_line_sensors()) to see the raw numbers behind the error

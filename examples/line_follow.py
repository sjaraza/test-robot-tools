#!/usr/bin/env python3
"""Follow a black line on the floor.

Run it on the robot:

    python3 ~/test-robot-tools/examples/line_follow.py

Press Ctrl-C to stop. The motors always stop when the script ends.

Before you start, check what the sensors actually see. Put the robot on the line
and run:

    python3 -c "import roboshine as r; print(r.get_line_sensors())"

The reading under the line should be clearly lower than the other two -- lower
means darker. If all three look the same, the line isn't under the sensors, so
move the robot.
"""

import roboshine as robot

SPEED = 15          # slow. A fast line follower overshoots every corner.
GAIN = 25           # how hard to steer. The number worth playing with
CHECK_EVERY = 0.05  # seconds between looks at the sensors
LOST_LIMIT = 20     # about a second of seeing nothing before giving up

print("Following the line. Ctrl-C to stop.")
print("Put the robot on the line before it starts moving.")
robot.wait(2)

robot.steerStraight()
robot.driveForward(SPEED)

lost_count = 0

try:
    while True:
        turn = robot.get_line(GAIN)

        if turn is None:
            # None means the three sensors read too much alike to tell where the
            # line is. Keep the last steering angle for a moment in case it's a
            # gap in the tape, rather than stopping at every join.
            lost_count += 1
            if lost_count > LOST_LIMIT:
                print("\nLost the line. Stopping.")
                break
        else:
            lost_count = 0

            # turn is negative when the line is off to the left and positive when
            # it's off to the right -- the same direction steer() uses, so it goes
            # straight in with no minus sign to get the wrong way round. The
            # further off the line, the bigger the number, so gentle drifts get
            # gentle corrections.
            robot.steer(turn)

            print(f"steer {turn:+6.1f}°   ", end="\r")

        robot.wait(CHECK_EVERY)

except KeyboardInterrupt:
    print("\nStopped by you.")

robot.stop()
robot.steerStraight()

# Things to try:
#   * raise GAIN until it starts wobbling, then back off a little -- that's about
#     as hard as it can correct on your floor
#   * raise SPEED once the steering looks steady
#   * lower CHECK_EVERY so it reacts more often
#   * watch the numbers behind the steering:
#       print(robot.get_line_sensors(), robot.get_line())
#   * ease into the new angle instead of jumping to it, which wobbles less:
#       robot.steer(robot.get_steer_angle() * 0.6 + turn * 0.4)
#   * stop when something is in the way too:
#       if 0 < robot.get_distance_cm() < 15: break

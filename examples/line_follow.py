#!/usr/bin/env python3
"""Follow a black line on the floor.

Run it on the robot:

    python3 ~/test-robot-tools/examples/line_follow.py

Press Ctrl-C to stop. The motors always stop when the script ends.

roboshine hands you the three sensor readings and nothing else -- deciding what
they mean is this script's job, and the interesting part. Read it, then change it.

Before you start, look at what the sensors actually see. Put the robot on the line
and run:

    python3 -c "import roboshine as r; print(r.read_line_sensors())"

You get something like {'L': 812, 'C': 240, 'R': 795}. Lower means darker, so the
reading under the line should be clearly lower than the other two. If all three
look the same, the line isn't under the sensors -- move the robot.
"""

import time

import roboshine as robot

SPEED = 150         # slow. A fast line follower overshoots every corner.
                    # 0 to 1000; try 80 if it still overshoots
TURN = 15           # how hard to steer when the line drifts to one side
MARGIN = 50         # how different the readings must be to count as seeing a line
CHECK_EVERY = 0.05  # seconds between looks at the sensors
LOST_LIMIT = 20     # about a second of seeing nothing before giving up

print("Following the line. Ctrl-C to stop.")
print("Put the robot on the line before it starts moving.")
time.sleep(2)

robot.steerStraight()
robot.driveForward(SPEED)

lost_count = 0

try:
    while True:
        sensors = robot.read_line_sensors()
        left = sensors["L"]
        centre = sensors["C"]
        right = sensors["R"]

        darkest = min(left, centre, right)
        brightest = max(left, centre, right)

        # If all three readings are close together there's nothing to steer by:
        # either the line isn't under the robot, or all three are on it. Comparing
        # the sensors against each other like this means there's nothing to
        # calibrate for your floor.
        if brightest - darkest < MARGIN:
            lost_count += 1
            if lost_count > LOST_LIMIT:
                print("\nLost the line. Stopping.")
                break

        else:
            lost_count = 0

            # The darkest sensor is the one over the line.
            if darkest == left:
                robot.steerLeft(TURN)
                where = "left  "
            elif darkest == right:
                robot.steerRight(TURN)
                where = "right "
            else:
                robot.steerStraight()
                where = "centre"

            print(f"line {where}  {sensors}", end="\r")

        time.sleep(CHECK_EVERY)

except KeyboardInterrupt:
    print("\nStopped by you.")

robot.stop()
robot.steerStraight()

# Things to try:
#   * raise SPEED and see where it starts overshooting corners
#   * raise TURN for sharper corrections -- too high and it wobbles
#   * lower CHECK_EVERY so it reacts more often
#   * this steers by the same amount however far off the line it is, which is why
#     it wobbles. Work out *how far* off it is and steer in proportion:
#         steer() takes any angle from -30 to 30, so you can calculate one
#   * stop when something is in the way too:
#         if 0 < robot.get_distance_cm() < 15: break
#   * if it steers the wrong way, check the sensors are the way round roboshine
#     thinks: python3 -c "import roboshine as r; r.checkLineSensors()"

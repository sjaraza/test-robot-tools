#!/usr/bin/env python3
"""Follow a black line on the floor.

Run it on the robot:

    python3 ~/test-robot-tools/examples/line_follow.py

Press Ctrl-C to stop. The motors always stop when the script ends.

Before you start, check what the sensors actually see. Put the robot on the line
and run:

    python3 -c "import roboshine as r; print(r.get_line_sensors())"

The number under the line should be clearly lower than the other two. If all
three look the same, the line isn't under the sensors -- move the robot.
"""

import roboshine as robot

SPEED = 15          # slow. A fast line follower overshoots every corner.
TURN = 15           # how hard to steer when the line drifts to one side
CHECK_EVERY = 0.05  # seconds between looks at the sensors

print("Following the line. Ctrl-C to stop.")
print("Put the robot on the line before it starts moving.")
robot.wait(2)

robot.steerStraight()
robot.driveForward(SPEED)

lost_count = 0

try:
    while True:
        where = robot.get_line_position()

        if where == "left":
            robot.steerLeft(TURN)
            lost_count = 0

        elif where == "right":
            robot.steerRight(TURN)
            lost_count = 0

        elif where == "centre":
            robot.steerStraight()
            lost_count = 0

        else:
            # 'lost' -- no sensor can pick the line out. Keep going briefly in
            # case it's a gap in the tape, but stop if it stays lost, rather than
            # driving off across the room.
            lost_count += 1
            if lost_count > 20:            # about one second
                print("Lost the line. Stopping.")
                break

        robot.wait(CHECK_EVERY)

except KeyboardInterrupt:
    print("\nStopped by you.")

robot.stop()
robot.steerStraight()

# Things to try:
#   * raise SPEED and see where it starts overshooting corners
#   * raise TURN for sharper corrections -- too high and it wobbles
#   * lower CHECK_EVERY so it reacts more often
#   * print(robot.get_line_sensors()) inside the loop to watch the numbers
#   * stop when something is in the way too:
#       if robot.get_distance_cm() > 0 and robot.get_distance_cm() < 15: break

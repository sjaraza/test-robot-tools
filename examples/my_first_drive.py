#!/usr/bin/env python3
"""A first robot script. Copy this, then change it.

Run it on the robot:

    python3 ~/test-robot-tools/examples/my_first_drive.py

Every command comes from roboshine. To see the full list:

    python3 -c "import roboshine; roboshine.showHelp()"
"""

import roboshine as robot

# What can we see in front of us?
space = robot.get_distance_cm()
print(f"There is {space} cm in front of me.")

if space < 0:
    print("Nothing close enough to measure -- plenty of room.")
    robot.driveForward(20)
    robot.wait(2)
    robot.stop()

elif space < 20:
    print("Something is close. Backing up instead.")
    robot.driveBack(20)
    robot.wait(1)
    robot.stop()

else:
    print("Room to move. Driving forward, then curving left.")
    robot.driveForward(20)
    robot.wait(2)

    # Steering and driving are separate commands, so a curve is two steps:
    # point the wheels, then drive. driveForward leaves the steering alone --
    # and the robot never stopped, it just started curving.
    robot.steerLeft(20)
    robot.wait(1)

    robot.stop()
    robot.steerStraight()

# Point the camera around -- this doesn't move the robot at all.
robot.lookLeft(40)
robot.wait(1)
robot.lookUp(20)          # now pointing up AND left; the two axes are separate
robot.wait(1)
robot.lookStraight()

print("Done.")

# Nothing blocks except wait(), so your script can watch while the robot moves:
#
#   robot.driveForward(15)
#   while robot.get_distance_cm() > 25:
#       robot.wait(0.1)
#   robot.stop()
#   print("Stopped because something got close.")
#
# Things to try:
#   * change the speeds and the wait times
#   * curve the other way with steerRight(20)
#   * a gentler curve: steerLeft(10) instead of steerLeft(20)
#   * uncomment the loop above and drive it at a wall

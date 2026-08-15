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
    robot.drive('f', 20, seconds=2)

elif space < 20:
    print("Something is close. Backing up instead.")
    robot.drive('b', 20, seconds=1)

else:
    print("Room to move. Driving forward, then curving left.")
    robot.drive('f', 20, seconds=2)
    robot.drive('l', 20, seconds=1)

robot.stop()
print("Done.")

# Things to try:
#   * change the speeds and the seconds
#   * curve right with 'r' instead of 'l'
#   * loop: keep driving forward while get_distance_cm() stays above 30
#   * use robot.steer(-20) to point the wheels without driving

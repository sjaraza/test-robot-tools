#!/usr/bin/env python3
"""Follow the line around the arena.

    python3 ~/test-robot-tools/examples/arena_lap.py

Put the robot on the line at Start, facing along the line. Ctrl-C to stop.
"""

import time

import roboshine as robot

SPEED = 150          # 0 to 1000
TURN = 30            # full lock. The corners are too tight for anything gentler
CONTRAST = 200       # how much darker than the floor the line reads
LOOK_EVERY = 0.05    # seconds between looks at the sensors
GIVE_UP_AFTER = 60   # looks with no line at all before stopping (about 3s)

input("Put the robot on the floor, away from the line, then press Enter: ")
floor = robot.read_line_sensors()
average = (floor["L"] + floor["C"] + floor["R"]) / 3
dark_below = average - CONTRAST
print(f"floor reads about {average:.0f}, so the line is anything below {dark_below:.0f}")

input("Now put the robot on the line at Start, then press Enter: ")

robot.steerStraight()
robot.driveForward(SPEED)

missing = 0

try:
    while True:
        sensors = robot.read_line_sensors()

        left = sensors["L"] < dark_below      # True when that sensor sees the line
        centre = sensors["C"] < dark_below
        right = sensors["R"] < dark_below

        if left:
            robot.steerLeft(TURN)             # checked first, so junctions go left
            missing = 0

        elif centre:
            robot.steerStraight()             # dead on
            missing = 0

        elif right:
            robot.steerRight(TURN)            # line has drifted to the right
            missing = 0

        else:
            robot.steerLeft(TURN)             # nothing: keep turning until we find it
            missing = missing + 1
            if missing > GIVE_UP_AFTER:
                print("Lost the line. Stopping.")
                break

        time.sleep(LOOK_EVERY)

except KeyboardInterrupt:
    print("Stopped by you.")

robot.stop()
robot.steerStraight()

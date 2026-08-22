"""Per-robot settings, shared by roboshine and the cockpit.

One small JSON file in the student's home directory:

    ~/.roboshine.json       {"drive_flipped": true}

It lives here rather than in the repo so that `update` can't overwrite it, and
per robot rather than per script because it describes how *that* robot is wired.

Only one setting so far. `drive_flipped` says whether picarx's forward() drives
this particular car backwards -- which depends on which way round the motor wires
were pushed on when it was built, so it genuinely varies between robots. It is a
setting rather than a constant because of that.

Kept in its own module so the cockpit and roboshine read and write the same file
the same way, instead of each having its own opinion about the format.
"""

import json
import os

CONFIG_PATH = os.path.expanduser("~/.roboshine.json")

# What the robots that have been checked so far turned out to need. A robot whose
# motors are wired the other way round is one `flipDrive()` away from being right,
# and stays that way.
DEFAULT_DRIVE_FLIPPED = True

_cache = None


def load():
    """The settings as a dict. Never raises -- a missing or broken file is
    treated as "no settings yet", because a student's robot should still drive
    with a corrupt config rather than refuse to start."""
    global _cache
    if _cache is not None:
        return _cache

    try:
        with open(CONFIG_PATH) as handle:
            data = json.load(handle)
        _cache = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        _cache = {}
    return _cache


def save(settings):
    """Write the settings out. Returns the path, or raises OSError."""
    global _cache

    # Write then rename, so an interrupted write can't leave a half-written file
    # that reads as "no settings" the next time.
    temporary = CONFIG_PATH + ".new"
    with open(temporary, "w") as handle:
        json.dump(settings, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, CONFIG_PATH)

    _cache = dict(settings)
    return CONFIG_PATH


def drive_flipped():
    """True when picarx's forward() drives this robot backwards."""
    return bool(load().get("drive_flipped", DEFAULT_DRIVE_FLIPPED))


def set_drive_flipped(flipped):
    """Remember whether this robot's motors are wired mirrored. Returns the new
    value."""
    settings = dict(load())
    settings["drive_flipped"] = bool(flipped)
    save(settings)
    return bool(flipped)


def forget():
    """Drop the cached copy, so the next read comes from the file again.

    The cockpit and a student's script are separate processes, so this only
    matters within one of them -- but the cockpit changes the setting and then
    keeps running, and it should drive the new way immediately.
    """
    global _cache
    _cache = None

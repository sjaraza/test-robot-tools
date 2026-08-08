#!/usr/bin/env python3
"""Recover a robot that can't be SSHed into, by editing its card on a Mac.

    ./recover-ssh.py

Use when `ssh` gives "Connection refused": the robot is up but sshd won't start,
almost always because its host keys are missing.

You can't fix that by mounting the card -- the Linux filesystem is unreachable
from macOS. But cloud-init takes its orders from the FAT boot partition, so we
add a runcmd that regenerates the keys and bump the instance-id to make
cloud-init treat the next boot as a new machine and actually run it.

Steps:
  1. power the robot down, put its card in this Mac
  2. run this script
  3. eject, put the card back, power on, wait about two minutes
  4. ssh-keygen -R robot-N.local     (its host keys will be new)
  5. ssh robot@robot-N.local
"""

import argparse
import os
import re
import secrets
import sys

BOOT_CANDIDATES = ("/Volumes/bootfs", "/Volumes/boot")

FIX_LINES = [
    '  - [ sh, -c, "ssh-keygen -A" ]',
    '  - [ sh, -c, "systemctl enable --now ssh" ]',
]


def find_card():
    for path in BOOT_CANDIDATES:
        if os.path.isdir(path):
            return path
    sys.exit("no card found under /Volumes. Insert it and try again.")


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def add_fix(card):
    path = os.path.join(card, "user-data")
    text = read(path)

    if "ssh-keygen -A" in text:
        return "user-data      already carries the ssh-keygen fix"

    block = "\n".join(FIX_LINES)
    if re.search(r"(?m)^runcmd:\s*$", text):
        # Put ours first so ssh comes back as early as possible.
        text = re.sub(r"(?m)^runcmd:\s*$", "runcmd:\n" + block, text, count=1)
    else:
        text = text.rstrip("\n") + "\nruncmd:\n" + block + "\n"
    write(path, text)
    return "user-data      added ssh-keygen -A to runcmd"


def bump_instance(card):
    """Any new value works; cloud-init only cares that it changed."""
    suffix = secrets.token_hex(3)
    notes = []

    path = os.path.join(card, "meta-data")
    text = read(path)
    match = re.search(r"(?m)^instance-id:\s*(\S+)", text)
    current = match.group(1) if match else "unknown"
    new_id = f"{current.split('-recover')[0]}-recover{suffix}"
    if match:
        text = re.sub(r"(?m)^instance-id:.*$", f"instance-id: {new_id}", text)
    else:
        text = text.rstrip("\n") + f"\ninstance-id: {new_id}\n"
    write(path, text)
    notes.append(f"meta-data      instance-id: {new_id}")

    path = os.path.join(card, "cmdline.txt")
    text = read(path)
    if "ds=nocloud" in text:
        # Must stay one line with no trailing newline.
        text = re.sub(r"(ds=nocloud[^\s]*?;i=)[^\s;]+", r"\g<1>" + new_id, text)
        write(path, text.replace("\n", "").replace("\r", ""))
        notes.append(f"cmdline.txt    i={new_id}")
    return notes


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--card", help="path to the boot partition")
    args = parser.parse_args()

    card = args.card or find_card()
    for name in ("user-data", "meta-data", "cmdline.txt"):
        if not os.path.isfile(os.path.join(card, name)):
            sys.exit(f"{card}/{name} missing -- wrong partition?")

    print(f"patching {card}\n")
    notes = [add_fix(card)] + bump_instance(card)
    for note in notes:
        print("  " + note)

    print(f"\nEject:  diskutil eject {card}")
    print("Then boot the robot, wait ~2 minutes, and:")
    print("  ssh-keygen -R robot-1.local && ssh robot@robot-1.local")


if __name__ == "__main__":
    main()

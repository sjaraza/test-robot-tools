#!/usr/bin/env python3
"""Stamp a freshly cloned SD card with its robot identity. Run on your Mac.

    ./stamp-card.py 7
    ./stamp-card.py 7 --mac-offset 0     # if robot-1 is ...:00 rather than :01

Everything it edits lives on the card's FAT boot partition, which is the only
partition macOS can mount -- the Linux rootfs is unreachable from here. That's
fine, because this image is customised by cloud-init and all of cloud-init's
inputs are on that FAT partition:

    user-data       hostname
    meta-data       instance-id
    cmdline.txt     ds=nocloud;i=<instance-id>   (seeded before meta-data)
    network-config  netplan, including the wlan0 MAC

Changing the instance-id is what makes cloud-init treat the clone as a brand new
machine and re-run its per-instance modules -- which also means it regenerates
the SSH host keys, so nineteen robots don't all share robot-1's identity.
"""

import argparse
import os
import re
import sys

BOOT_CANDIDATES = ("/Volumes/bootfs", "/Volumes/boot")
MAC_PREFIX = "aa:bb:cc:dd:ee"


def find_card():
    for path in BOOT_CANDIDATES:
        if os.path.isdir(path):
            return path
    sys.exit("no card found under /Volumes. Insert it and try again.\n"
             f"  looked for: {', '.join(BOOT_CANDIDATES)}")


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def set_hostname(card, hostname):
    path = os.path.join(card, "user-data")
    text = read(path)
    if not re.search(r"(?m)^hostname:", text):
        sys.exit(f"{path} has no 'hostname:' line -- is this a cloud-init card?")
    text = re.sub(r"(?m)^hostname:.*$", f"hostname: {hostname}", text)
    write(path, text)
    return "user-data      hostname: " + hostname


def set_instance_id(card, instance_id):
    """Both places, because cmdline is seeded ahead of meta-data."""
    notes = []

    path = os.path.join(card, "meta-data")
    text = read(path)
    if re.search(r"(?m)^instance-id:", text):
        text = re.sub(r"(?m)^instance-id:.*$", f"instance-id: {instance_id}", text)
    else:
        text = text.rstrip("\n") + f"\ninstance-id: {instance_id}\n"
    write(path, text)
    notes.append("meta-data      instance-id: " + instance_id)

    path = os.path.join(card, "cmdline.txt")
    text = read(path)
    if "ds=nocloud" not in text:
        sys.exit(f"{path} has no ds=nocloud -- this card isn't cloud-init seeded")
    # cmdline.txt must remain ONE line with no trailing newline. The stock file
    # from Raspberry Pi Imager has none, and adding one can break boot.
    new_text = re.sub(r"(ds=nocloud[^\s]*?;i=)[^\s;]+", r"\g<1>" + instance_id, text)
    if new_text == text:
        new_text = re.sub(r"(ds=nocloud)(?![^\s]*;i=)", r"\g<1>;i=" + instance_id,
                          text)
    new_text = new_text.replace("\n", "").replace("\r", "")
    write(path, new_text)
    notes.append("cmdline.txt    i=" + instance_id)
    return notes


def set_mac(card, mac):
    """Put the MAC in the netplan block that already configures wlan0."""
    path = os.path.join(card, "network-config")
    text = read(path)
    if not re.search(r"(?m)^\s+wlan0:", text):
        sys.exit(f"{path} has no wlan0 block")

    # Replace an existing macaddress under wlan0, or insert one right after it,
    # matching the surrounding indentation.
    match = re.search(r"(?m)^(\s+)wlan0:[ \t]*$", text)
    indent = match.group(1) + "  "

    if re.search(r"(?m)^\s+macaddress:", text):
        text = re.sub(r"(?m)^(\s+)macaddress:.*$", r"\g<1>macaddress: " + mac, text)
    else:
        text = text[:match.end()] + f"\n{indent}macaddress: {mac}" + text[match.end():]
    write(path, text)
    return "network-config macaddress: " + mac


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("number", type=int, nargs="?",
                        help="robot number, e.g. 7")
    parser.add_argument("--mac-prefix", default=MAC_PREFIX)
    parser.add_argument("--base", type=int, default=0,
                        help="last octet for robot-1. Default 0, matching "
                             "robot-1 = ...:00, so robot-N is N-1")
    parser.add_argument("--card", help="path to the boot partition")
    parser.add_argument("--table", type=int, metavar="COUNT",
                        help="print the hostname/MAC table for COUNT robots and "
                             "exit, without touching a card")
    args = parser.parse_args()

    if args.table:
        print("robot        MAC")
        for number in range(1, args.table + 1):
            print(f"  robot-{number:<6} {octet_mac(args, number)}")
        return

    if args.number is None:
        parser.error("give a robot number, or --table COUNT")
    if not 1 <= args.number <= 99:
        sys.exit("robot number must be 1-99")

    card = args.card or find_card()
    hostname = f"robot-{args.number}"
    mac = octet_mac(args, args.number)

    for path in ("user-data", "meta-data", "cmdline.txt", "network-config"):
        full = os.path.join(card, path)
        if not os.path.isfile(full):
            sys.exit(f"{full} is missing -- is this the right partition?")

    print(f"stamping {card} as {hostname}\n")
    notes = [set_hostname(card, hostname)]
    notes += set_instance_id(card, hostname)
    notes.append(set_mac(card, mac))
    for note in notes:
        print("  " + note)

    print(f"\ndone. Eject with:  diskutil eject {card}")


def octet_mac(args, number):
    """robot-1 -> base, robot-2 -> base+1, ...

    Zero-padded decimal digits used literally as a hex octet, so robot-19 reads
    as ...:18 rather than ...:12. Real hex would invite mistakes when typing
    router reservations by hand.
    """
    octet = args.base + number - 1
    if not 0 <= octet <= 99:
        sys.exit(f"robot-{number} would need octet {octet}, out of range")
    return f"{args.mac_prefix}:{octet:02d}"


if __name__ == "__main__":
    main()

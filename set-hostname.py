#!/usr/bin/env python3
"""Set the hostname on a freshly flashed SD card. Run on your Mac.

    ./set-hostname.py 7            -> robot-7
    ./set-hostname.py --name foo   -> foo
    ./set-hostname.py 7 --dry-run  -> show the change, write nothing

Only touches `user-data` on the FAT boot partition, which is where Raspberry Pi
Imager's cloud-init customisation keeps the hostname. Deliberately does NOT touch
cmdline.txt or meta-data:

* A brand-new card has never booted, so cloud-init will apply user-data on its
  first boot regardless -- there is no instance-id to bump.
* cmdline.txt is the file that must stay a single line with no trailing newline,
  and rewriting it on macOS 26's FSKit FAT driver corrupted a card once. Not
  worth the risk when it buys nothing here.

Writes go to a temp file and are renamed into place, then read back and compared.
A truncating write straight onto the target is what corrupted that card.
"""

import argparse
import glob
import os
import re
import shutil
import sys

# Files that tell us we're looking at a Raspberry Pi boot partition.
MARKERS = ("config.txt", "cmdline.txt")


def find_card():
    """Find the boot partition, ignoring stale empty mount points.

    macOS leaves behind empty directories in /Volumes, and a second card with the
    same label mounts as "bootfs 1" -- so look for the marker files rather than
    trusting a directory name.
    """
    found = []
    for entry in sorted(glob.glob("/Volumes/*")):
        if any(os.path.isfile(os.path.join(entry, m)) for m in MARKERS):
            found.append(entry)

    if len(found) == 1:
        return found[0]
    if not found:
        print("No Raspberry Pi boot partition found. Mounted volumes:",
              file=sys.stderr)
        for entry in sorted(glob.glob("/Volumes/*")):
            print(f"  {entry}", file=sys.stderr)
        sys.exit("Insert the card, or pass --card /Volumes/<name>")
    sys.exit("Several cards are mounted; pick one with --card:\n  "
             + "\n  ".join(found))


def atomic_write(path, text):
    """Write via temp file and rename, then verify by reading back."""
    directory = os.path.dirname(path)
    temp = os.path.join(directory, ".tmp-" + os.path.basename(path))
    try:
        with open(temp, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except OSError as exc:
        if os.path.exists(temp):
            os.remove(temp)
        sys.exit(f"write failed: {exc}\n"
                 "If this says 'Invalid argument', the FAT partition may be\n"
                 "corrupt. Unmount it and run: sudo fsck_msdos -y /dev/diskNsM")

    with open(path, encoding="utf-8") as handle:
        got = handle.read()
    if got != text:
        sys.exit(f"{path} did not read back as written -- do not boot this card.\n"
                 "Run fsck_msdos on the partition before using it.")

    # macOS drops AppleDouble sidecars on FAT; harmless to the Pi, but untidy.
    sidecar = os.path.join(directory, "._" + os.path.basename(path))
    if os.path.exists(sidecar):
        try:
            os.remove(sidecar)
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("number", type=int, nargs="?",
                        help="robot number, becomes robot-<N>")
    parser.add_argument("--name", help="use this hostname verbatim")
    parser.add_argument("--card", help="path to the boot partition")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.name:
        hostname = args.name
    elif args.number is not None:
        if not 1 <= args.number <= 99:
            sys.exit("robot number must be 1-99")
        hostname = f"robot-{args.number}"
    else:
        parser.error("give a robot number, or --name")

    if not re.fullmatch(r"[a-zA-Z0-9-]{1,63}", hostname) or hostname.startswith("-"):
        sys.exit(f"'{hostname}' isn't a valid hostname (letters, digits, hyphens)")

    card = args.card or find_card()
    path = os.path.join(card, "user-data")

    if not os.path.isfile(path):
        sys.exit(f"{card} has no user-data.\n"
                 "This card wasn't flashed with Raspberry Pi Imager's OS\n"
                 "customisation, so there's no cloud-init config to edit.\n"
                 "Re-flash with customisation enabled (hostname, user, WiFi).")

    text = open(path, encoding="utf-8").read()
    current = re.search(r"(?m)^hostname:\s*(\S+)", text)

    if current and current.group(1) == hostname:
        print(f"{card} is already set to {hostname} -- nothing to do")
        return

    if current:
        new_text = re.sub(r"(?m)^hostname:.*$", f"hostname: {hostname}", text,
                          count=1)
        was = current.group(1)
    else:
        # Put it after the #cloud-config line so the file stays readable.
        lines = text.splitlines(keepends=True)
        insert_at = 1 if lines and lines[0].startswith("#cloud-config") else 0
        lines.insert(insert_at, f"hostname: {hostname}\n")
        new_text = "".join(lines)
        was = "(not set)"

    print(f"card     {card}")
    print(f"hostname {was}  ->  {hostname}")

    if args.dry_run:
        print("\n--dry-run, nothing written")
        return

    backup = path + ".orig"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
        print(f"backed up original to {os.path.basename(backup)}")

    atomic_write(path, new_text)
    print("written and verified")
    print(f"\nEject with:  diskutil eject {card}")


if __name__ == "__main__":
    main()

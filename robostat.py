#!/usr/bin/env python3
"""Print this robot's stats and exit. This is what the `robostat` alias runs.

    robostat            one snapshot
    robostat --watch    refresh every 2 seconds until Ctrl-C

All the reading logic is reused from robotmenu.py, so the numbers here and in
the menu can never drift apart.
"""

import argparse
import time

import robotmenu as rm


def render(width=None):
    """Return the framed stats block as a list of lines."""
    if width is None:
        width = min(rm.shutil.get_terminal_size((60, 24)).columns, 60)
    inner = width - 4
    half = (inner - 2) // 2
    side = rm.paint("│", rm.fg(rm.gradient_colour(0.5))) if rm.COLOUR else "│"

    # Read everything before building any output, so library chatter can't land
    # inside the frame.
    stats = rm.dashboard_lines()

    lines = [rm.gradient_text("╭" + "─" * (width - 2) + "╮")]

    title = rm.robot_name()
    lines.append(side + " " + rm.pad(rm.gradient_text(title, bold=True), inner)
                 + " " + side)
    lines.append(rm.gradient_text("├" + "─" * (width - 2) + "┤"))

    for index in range(0, len(stats), 2):
        label, value = stats[index]
        left = rm.cell(label, value, half)
        if index + 1 < len(stats):
            right_label, right_value = stats[index + 1]
            right = rm.cell(right_label, right_value, half)
        else:
            right = ""
        lines.append(side + " " + rm.pad(left + "  " + right, inner) + " " + side)

    lines.append(rm.gradient_text("╰" + "─" * (width - 2) + "╯"))
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--watch", action="store_true",
                        help="keep refreshing until Ctrl-C")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="seconds between refreshes with --watch")
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args()

    if args.no_color:
        rm.COLOUR = False

    if not args.watch:
        print("\n".join(render()))
        return

    try:
        while True:
            rm.clear_screen()
            print("\n".join(render()))
            print(rm.paint("  Ctrl-C to stop", rm.GREY))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()

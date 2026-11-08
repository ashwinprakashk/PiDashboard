#!/usr/bin/env python3
"""Write a message to flag.txt; the running dashboard shows it with a fireworks show.

Usage:  python3 String_trigger_script.py "Dinner is ready!"
"""
import os
import sys

FLAG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flag.txt")


def write_message(msg: str):
    with open(FLAG_FILE, "w") as f:
        f.write(msg)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        write_message(" ".join(sys.argv[1:]))
    else:
        write_message("Launch by Unknown")
    print("Message written.")

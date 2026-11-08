#!/bin/bash
# Waits for an internet connection, then starts the dashboard from this script's folder.

cd "$(dirname "$(readlink -f "$0")")"

echo "Checking Internet connectivity..."
while ! ping -c1 8.8.8.8 >/dev/null 2>&1; do
    echo "Waiting for Internet..."
    sleep 2
done

echo "Internet is online. Starting dashboard..."
exec /usr/bin/python3 fan_clock_display.py

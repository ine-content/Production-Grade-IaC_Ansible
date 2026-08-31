#!/usr/bin/env bash
# setup_local_loopback.sh - one-time local setup for running
# mock_device_server.py on macOS.
#
# Linux treats the entire 127.0.0.0/8 range as loopback automatically -
# no setup needed there, and none needed on a real GitLab CI runner
# either, since GitLab's shared/Docker runners are always Linux. macOS
# only configures 127.0.0.1 on lo0 by default; every other address in
# 127.0.0.0/8 needs to be added as an alias first, or binding to it fails
# with "Can't assign requested address".
#
# This script reads every IP address out of devices/*.json (never
# hardcoded) and, on macOS, adds each one as a loopback alias. On Linux
# it does nothing, since nothing is needed.
#
# Usage:
#   sudo ./setup_local_loopback.sh
#
# The aliases this adds do not survive a reboot - macOS resets lo0 back
# to just 127.0.0.1 on every restart, so re-run this once after each
# reboot before running mock_device_server.py locally.

set -euo pipefail

cd "$(dirname "$0")"

IPS=$(python3 -c "
import json, glob
ips = set()
for f in glob.glob('devices/*.json'):
    for d in json.load(open(f)):
        ips.add(d['ip_address'])
print('\n'.join(sorted(ips)))
")

if [ -z "$IPS" ]; then
    echo "No devices found under devices/*.json - nothing to do."
    exit 0
fi

case "$(uname)" in
    Darwin)
        if [ "$(id -u)" -ne 0 ]; then
            echo "This needs sudo on macOS (adding aliases to lo0). Re-run as:"
            echo "  sudo ./setup_local_loopback.sh"
            exit 1
        fi
        echo "macOS detected - adding loopback aliases to lo0:"
        while IFS= read -r ip; do
            if [ "$ip" = "127.0.0.1" ]; then
                continue
            fi
            ifconfig lo0 alias "$ip" up
            echo "  added $ip"
        done <<< "$IPS"
        echo "Done. These aliases last until the next reboot."
        ;;
    Linux)
        echo "Linux detected - the entire 127.0.0.0/8 range is loopback-routable"
        echo "here by default (same as on a GitLab CI runner). Nothing to do."
        ;;
    *)
        echo "Unrecognized OS ($(uname)). If mock_device_server.py fails with"
        echo "\"Can't assign requested address\", your OS likely needs each of"
        echo "these IPs added as a loopback alias, the same way macOS does:"
        echo "$IPS"
        ;;
esac

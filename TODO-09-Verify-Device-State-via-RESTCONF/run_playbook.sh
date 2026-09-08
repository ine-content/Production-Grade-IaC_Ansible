#!/usr/bin/env bash
# run_playbook.sh - convenience wrapper for running this lab's site.yml by
# hand, outside the grader.
#
# Two things ansible-playbook does NOT do on its own, that this script
# handles for you every time:
#
#   1. Start the mock RESTCONF device fleet. ansible-playbook only talks
#      to whatever's already listening at ansible_host:restconf_port - it
#      has no idea mock_device_server.py exists, same as it would never
#      power on a real switch for you. This script starts it (in the
#      background, logging to logs/mock_device_server.log), waits for it
#      to come up, and stops it again when the playbook finishes - even
#      if the playbook fails. Any mock_device_server.py already running
#      (e.g. one you started yourself in another terminal) is stopped
#      first, so you're never accidentally talking to a second fleet with
#      different credentials than the one this script starts.
#
#      mock_device_state.json (this fleet's persisted "device memory") is
#      never touched by this script - stopping and restarting the process
#      between runs does not reset it, so drift you introduced in an
#      earlier run is still there to see in the next one.
#
#   2. Export .env into the shell. ansible-playbook does not read .env
#      files itself - only mock_device_server.py does. Without this,
#      RESTCONF_*_USERNAME / RESTCONF_*_PASSWORD from .env never reach a
#      task's lookup('env', ...) calls.
#
# You do NOT need this for grading - python grading.py manages the mock
# fleet and sets its own test credentials directly, entirely separately
# from this script and from .env.
#
# Usage:
#   ./run_playbook.sh
#   ./run_playbook.sh --check          (any ansible-playbook flag works too)
#
# Want to watch the mock fleet's live log instead of just the file? Run
# `python mock_device_server.py` yourself in another terminal first, then
# use ansible-playbook directly instead of this script.

set -euo pipefail

cd "$(dirname "$0")"

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

mkdir -p logs

# Stop any mock fleet already running - never assume a leftover process is
# using the same credentials this run will.
pkill -f "mock_device_server.py" 2>/dev/null || true
sleep 0.5

python3 mock_device_server.py >> logs/mock_device_server.log 2>&1 &
MOCK_PID=$!
sleep 1.5   # every device server binds synchronously at startup

if ! kill -0 "$MOCK_PID" 2>/dev/null; then
    echo "ERROR: mock_device_server.py failed to start - see logs/mock_device_server.log" >&2
    if grep -q "Can't assign requested address" logs/mock_device_server.log 2>/dev/null; then
        echo "" >&2
        echo "This looks like the macOS loopback aliases haven't been set up yet." >&2
        echo "Run this once (needs sudo, and again after every reboot), then try again:" >&2
        echo "  sudo ./setup_local_loopback.sh" >&2
    fi
    exit 1
fi

cleanup() {
    kill "$MOCK_PID" 2>/dev/null || true
    wait "$MOCK_PID" 2>/dev/null || true
}
trap cleanup EXIT

ansible-playbook -i inventory/devices.py site.yml "$@"

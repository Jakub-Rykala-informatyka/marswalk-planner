#!/bin/bash
# Serves the dashboard on http://localhost:8080 and feeds it from ROS 2.
# Start the simulation first or afterwards with ./scripts/run_sim.sh
set -e

cd "$(dirname "${BASH_SOURCE[0]}")/.."
[ -t 0 ] || NO_TTY=-T

exec docker compose run --rm $NO_TTY ros2 python3 ros/telemetry_server.py "$@"

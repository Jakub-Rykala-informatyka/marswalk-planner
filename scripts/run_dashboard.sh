#!/bin/bash
# Starts the ROS 2 side in Docker: NASA layers, dose monitor, cost map, planner, suit monitor, mission planner and the dashboard
# on http://localhost:8080. Start the simulation with ./scripts/run_sim.sh
set -e

cd "$(dirname "${BASH_SOURCE[0]}")/.."
[ -t 0 ] || NO_TTY=-T

exec docker compose run --rm $NO_TTY ros2 bash -c \
    'python3 ros/nasa_layers.py & python3 ros/dose_monitor.py & python3 ros/costmap.py & python3 ros/planner.py & python3 ros/suit_monitor.py & python3 ros/mission_planner.py & exec python3 ros/telemetry_server.py "$@"' _ "$@"

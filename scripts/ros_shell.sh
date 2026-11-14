#!/bin/bash
# Opens a ROS 2 Humble shell (or runs a command) in Docker on the simulation's DDS domain.
# Usage: ./scripts/ros_shell.sh                       interactive shell
#        ./scripts/ros_shell.sh ros2 topic list       one command
set -e

cd "$(dirname "${BASH_SOURCE[0]}")/.."
[ -t 0 ] || NO_TTY=-T

exec docker compose run --rm $NO_TTY ros2 "${@:-bash}"

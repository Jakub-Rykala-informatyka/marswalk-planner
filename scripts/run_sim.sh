#!/bin/bash
# Runs the Marswalk simulation in Isaac Sim on the host, publishing to ROS 2.
# Usage: ./scripts/run_sim.sh [--camera astronaut] [--record] [--headless]
#
# Another Isaac Sim install: ISAAC_ROOT=/path/to/isaac ./scripts/run_sim.sh
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ISAAC_ROOT="${ISAAC_ROOT:-$HOME/Unitree_Project/IsaacSim/_build/linux-x86_64/release}"

export ROS_DISTRO=humble
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-43}"
export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:$ISAAC_ROOT/exts/isaacsim.ros2.bridge/humble/lib"

exec "$ISAAC_ROOT/python.sh" "$PROJECT_DIR/sim/run_rover.py" --ros "$@"

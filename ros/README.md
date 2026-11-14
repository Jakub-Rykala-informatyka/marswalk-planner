# ROS 2 side

ROS 2 Humble runs in Docker, Isaac Sim runs on the host. Both use DDS domain 43
over UDP (`ros/fastdds.xml` turns shared memory off, which does not cross the
container boundary).

## Run

```bash
./scripts/run_sim.sh                  # Isaac Sim window, astronaut walks the route, rover follows
./scripts/ros_shell.sh                # ROS 2 Humble shell on the same domain
./scripts/ros_shell.sh ros2 topic list
```

`run_sim.sh` passes its arguments on to `sim/run_rover.py`, for example
`--camera astronaut` for the view from eye level or `--route data/route.geojson`
for another route.

## Topics published by the simulation

| Topic | Type | Content |
| --- | --- | --- |
| `/clock` | `rosgraph_msgs/Clock` | simulation time |
| `/astronaut/pose` | `geometry_msgs/PoseStamped` | astronaut position on the ground and walking direction |
| `/rover/pose` | `geometry_msgs/PoseStamped` | rover position and heading, from physics |
| `/rover/state` | `std_msgs/String` | `following`, `waiting` or `arrived` |

Messages come 10 times per simulated second. The simulation runs at about 0.9 of
real time on the hackathon laptop.

## Frame

`frame_id` is `map`: local metres with the origin in the south-west corner of
the terrain patch, x east, y north, z up, where z = 0 is the lowest point of the
patch. This is the frame of `data/terrain/meta.json`, `data/meta.json` and the
route files, so a pose indexes the layers directly:
`layer[int(y / cell_m), int(x / cell_m)]`.

## Not here yet

Suit sensor nodes (oxygen, battery, dose), the cost map and the planner.

## Dashboard

`./scripts/run_dashboard.sh` starts `ros/telemetry_server.py`: a ROS 2 node that
serves the app on http://localhost:8080 and streams the topics above to the
browser over WebSocket (`/ws`), five messages per second.

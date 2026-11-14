# ROS 2 side

ROS 2 Humble runs in Docker, Isaac Sim runs on the host. Both use DDS domain 43
over UDP (`ros/fastdds.xml` turns shared memory off, which does not cross the
container boundary).

## Run

```bash
./scripts/run_dashboard.sh            # ROS 2 nodes below + dashboard on http://localhost:8080
./scripts/run_sim.sh                  # Isaac Sim window, astronaut walks the route, rover follows
./scripts/ros_shell.sh                # ROS 2 Humble shell on the same domain
./scripts/ros_shell.sh ros2 topic list
```

`run_sim.sh` passes its arguments on to `sim/run_rover.py`, for example
`--camera astronaut` for the view from eye level or `--route data/route.geojson`
for another route.

## Nodes

| Node | File | Subscribes | Publishes |
| --- | --- | --- | --- |
| `marswalk_sim` | `sim/run_rover.py` (Isaac Sim) | – | `/clock`, `/astronaut/pose`, `/rover/pose`, `/rover/state` |
| `nasa_layers` | `ros/nasa_layers.py` | – (reads `data/layers/`) | `/nasa/slope`, `/nasa/roughness`, `/nasa/sky_view`, `/nasa/dose_rate` |
| `dose_monitor` | `ros/dose_monitor.py` | `/nasa/dose_rate`, `/astronaut/pose` | `/astronaut/dose_rate`, `/astronaut/dose` |
| `marswalk_telemetry` | `ros/telemetry_server.py` | everything above | WebSocket `/ws` for the browser |

## NASA layer topics

`nav_msgs/OccupancyGrid`, published once with transient local durability
(subscribe with the same QoS, or `--qos-durability transient_local` in the CLI).
Cells are 2.02 m, row 0 is the south edge, the grid origin is half a cell
south-west of the map origin. Values are 0..100:

| Topic | 100 means | Source |
| --- | --- | --- |
| `/nasa/slope` | 45° or steeper | HiRISE DTM |
| `/nasa/roughness` | 1 m height spread or more | HiRISE DTM |
| `/nasa/sky_view` | open sky, no terrain above the horizon | HiRISE DTM |
| `/nasa/dose_rate` | 26.7 µSv/h, the open-ground rate measured by RAD | RAD on Curiosity × sky view |

The dose model is a simplification (cosmic rays only, scaled by open sky); its
limits are written in `data/meta.json` under `dose_model`.

## Topics published by the simulation

| Topic | Type | Content |
| --- | --- | --- |
| `/clock` | `rosgraph_msgs/Clock` | simulation time |
| `/astronaut/pose` | `geometry_msgs/PoseStamped` | astronaut position on the ground and walking direction |
| `/rover/pose` | `geometry_msgs/PoseStamped` | rover position and heading, from physics |
| `/rover/state` | `std_msgs/String` | `following`, `waiting` or `arrived` |
| `/astronaut/dose_rate` | `std_msgs/Float32` | µSv/h at the astronaut's position (from `dose_monitor`) |
| `/astronaut/dose` | `std_msgs/Float32` | µSv since the walk started (from `dose_monitor`) |

Messages come 10 times per simulated second. The simulation runs at about 0.9 of
real time on the hackathon laptop.

## Frame

`frame_id` is `map`: local metres with the origin in the south-west corner of
the terrain patch, x east, y north, z up, where z = 0 is the lowest point of the
patch. This is the frame of `data/terrain/meta.json`, `data/meta.json` and the
route files, so a pose indexes the layers directly:
`layer[int(y / cell_m), int(x / cell_m)]`.

## Not here yet

Suit sensor nodes for oxygen and battery, the cost map and the planner.

## Dashboard

`./scripts/run_dashboard.sh` starts `nasa_layers`, `dose_monitor` and
`ros/telemetry_server.py` in one container. The telemetry server serves the app
on http://localhost:8080 and streams the topics above to the browser over
WebSocket (`/ws`), five messages per second.

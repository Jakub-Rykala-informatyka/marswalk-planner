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
| `marswalk_sim` | `sim/run_rover.py` (Isaac Sim) | `/route` | `/clock`, `/astronaut/pose`, `/rover/pose`, `/rover/state` |
| sensor graph | `sim/sensors.py` (Isaac Sim) | – | `/rover/points`, `/rover/camera/image`, `/astronaut/camera/image`, `/rover/arm_camera/image` |
| rover arm | `sim/arm.py` (Isaac Sim) | `/rover/arm/command` | `/rover/arm/joint_states` |
| `nasa_layers` | `ros/nasa_layers.py` | – (reads `data/layers/`) | `/nasa/slope`, `/nasa/roughness`, `/nasa/sky_view`, `/nasa/dose_rate` |
| `dose_monitor` | `ros/dose_monitor.py` | `/nasa/dose_rate`, `/astronaut/pose` | `/astronaut/dose_rate`, `/astronaut/dose` |
| `costmap` | `ros/costmap.py` | `/nasa/slope`, `/nasa/roughness`, `/nasa/dose_rate` | `/costmap/walk`, `/costmap/rover` |
| `suit_monitor` | `ros/suit_monitor.py` | `/astronaut/pose`, `/nasa/slope` | `/suit/status`, `/suit/return_point` |
| `planner` | `ros/planner.py` | `/costmap/walk`, `/nasa/dose_rate`, `/astronaut/pose`, `/goal_pose` | `/route`, `/route/summary` |
| `marswalk_telemetry` | `ros/telemetry_server.py` | everything above | WebSocket `/ws` for the browser, `/goal_pose` from map clicks, `/rover/config` from the rover planner tab |

## NASA layer topics

`nav_msgs/OccupancyGrid`, published once with transient local durability
(subscribe with the same QoS, or `--qos-durability transient_local` in the CLI).
Cells are 2.02 m, row 0 is the south edge, the grid origin is half a cell
south-west of the map origin. Values are 0..100:

| Topic | 100 means | Source |
| --- | --- | --- |
| `/nasa/slope` | 45° or steeper | HiRISE DTM |
| `/nasa/roughness` | 2 m height spread or more | HiRISE DTM |
| `/nasa/sky_view` | open sky, no terrain above the horizon | HiRISE DTM |
| `/nasa/dose_rate` | 26.7 µSv/h, the open-ground rate measured by RAD | RAD on Curiosity × sky view |

The dose model is a simplification (cosmic rays only, scaled by open sky); its
limits are written in `data/meta.json` under `dose_model`.

## Cost maps

`/costmap/walk` and `/costmap/rover` are latched `nav_msgs/OccupancyGrid`s on the
same grid as `/nasa/*`: 0 = free, 1..99 = harder going, 100 = keep out (the
Nav2 convention). Each cell adds a slope term (mild below the comfort slope,
growing fast towards the limit), a roughness term and a dose term; a cell at
or over the slope or roughness limit is 100.

Defaults are assumptions to tune, not measured limits:

| Parameter | `walk` | `rover` |
| --- | --- | --- |
| `max_slope_deg` | 25 | 15 |
| `comfort_slope_deg` | 15 | 8 |
| `max_roughness_m` | 2.0 | 1.0 |
| `slope_weight` / `roughness_weight` / `dose_weight` | 70 / 15 / 10 | 70 / 25 / 0 |

The rover has no dose weight because the cabin shields the crew. Change a
value live and both maps are recomputed and redrawn on the dashboard:

```bash
./scripts/ros_shell.sh ros2 param set /costmap walk.max_slope_deg 20.0
```

## Planner

A* on `/costmap/walk`, merged into 2 × 2 blocks (about 4 m; a block takes its
highest cost, so a keep-out cell blocks it). A step costs its length times
`1 + cost / cost_scale`; cells at 100 are never entered. It plans:

- at start, from the `start_x/start_y` to the `goal_x/goal_y` parameters (the
  ends of `data/route_example.geojson`),
- on every `/goal_pose` (a click on the dashboard map, or RViz "2D Goal Pose"),
  from where the astronaut stands,
- whenever a cost map changes, for example after `ros2 param set /costmap ...`.

`/route` is a latched `nav_msgs/Path` in the `map` frame. `/route/summary` is a
`std_msgs/String` with JSON: `length_m`, `walk_time_s` (at 0.8 m/s, the
simulation's pace), `dose_uSv` (dose-rate layer along the route) and
`max_cost`, or `{"ok": false}` when no route avoids the keep-out cells.

The simulation waits up to 20 s for `/route` at start, then follows every new
route from the astronaut's current position.

## Topics published by the simulation

| Topic | Type | Content |
| --- | --- | --- |
| `/clock` | `rosgraph_msgs/Clock` | simulation time |
| `/astronaut/pose` | `geometry_msgs/PoseStamped` | astronaut position on the ground and walking direction |
| `/rover/pose` | `geometry_msgs/PoseStamped` | rover position and heading, from physics |
| `/rover/state` | `std_msgs/String` | `following`, `waiting` or `arrived` |
| `/astronaut/dose_rate` | `std_msgs/Float32` | µSv/h at the astronaut's position (from `dose_monitor`) |
| `/astronaut/dose` | `std_msgs/Float32` | µSv since the walk started (from `dose_monitor`) |
| `/rover/points` | `sensor_msgs/PointCloud2` | full scans of an RTX lidar (Ouster OS1, 32 channels) 0.45 m above the rover base, frame `rover_lidar`, about 2.4 Hz |
| `/rover/camera/image` | `sensor_msgs/Image` | rover front camera, 640 × 360 RGB |
| `/astronaut/camera/image` | `sensor_msgs/Image` | helmet camera at eye level, 640 × 360 RGB |

`/rover/pose` carries the rover's full attitude (the astronaut's only its heading),
so the lidar points can be put into the `map` frame.

## Rover arm

A Unitree Z1 arm (from the Isaac Sim asset library) is bolted to the helper
robot: its fixed joint to the world is re-attached to the rover's base link, so
the arm is part of the rover articulation. Joints `joint1`..`joint6`, limits
and named poses are in `data/arm_presets.json` (shared with the dashboard).

- `/rover/arm/command` (`sensor_msgs/JointState`): target angles in radians by
  joint name; joints not named keep their target.
- `/rover/arm/joint_states` (`sensor_msgs/JointState`): measured angles.
- `/rover/arm_camera/image`: operator view from behind the rover.

From the command line:

```bash
./scripts/ros_shell.sh ros2 topic pub --once /rover/arm/command sensor_msgs/msg/JointState "{name: [joint2, joint3], position: [1.2, -1.2]}"
```

In the dashboard, the Cameras tab has sliders per joint and preset buttons
(stow, forward, ground, sample box). The arm has no gripper: picking up a
sample is not simulated.

The Jackal asset has its own SICK lidar, whose beams were drawn into every
camera image; the simulation disables it and uses its Ouster lidar instead.
`--no-lidar` leaves that one out too.

## Suit and safe return

`suit_monitor` publishes `/suit/status`, a `std_msgs/String` with JSON:

```json
{"o2_pct": 99.8, "o2_left_min": 479.0, "battery_pct": 99.9, "walked_m": 27.0,
 "return_point": [1141.0, 834.0], "return_m": 27.0, "return_min": 0.6,
 "margin_min": 448.4, "turn_back": false, "slope_deg": 7.8}
```

Oxygen lasts `o2_hours` (8) at a steady walk on flat ground; standing uses
`rest_factor` (0.6) of that and each degree of slope adds `slope_factor` (4 %).
The return point is where the walk began (the parked crew rover); the way back
is the distance walked so far at `walk_speed`. `margin_min` is oxygen left minus
the walk back minus `reserve_min` (30), and `turn_back` is true when less than a
quarter of the reserve is spare. All of these are assumptions set as parameters.

Messages come 10 times per simulated second. The simulation runs at about 0.9 of
real time on the hackathon laptop.

## Frame

`frame_id` is `map`: local metres with the origin in the south-west corner of
the terrain patch, x east, y north, z up, where z = 0 is the lowest point of the
patch. This is the frame of `data/terrain/meta.json`, `data/meta.json` and the
route files, so a pose indexes the layers directly:
`layer[int(y / cell_m), int(x / cell_m)]`.

## Not here yet

A combined drive-and-walk plan on `/costmap/rover`, and a way back planned on the cost map instead of retracing the walk.

## Dashboard

`./scripts/run_dashboard.sh` starts `nasa_layers`, `dose_monitor`, `costmap`,
`planner`, `suit_monitor` and `ros/telemetry_server.py` in one container. The
telemetry server serves the app on http://localhost:8080 and streams the topics
above to the browser over WebSocket (`/ws`), five messages per second. Bulk data
has its own endpoints, fetched when the WebSocket message says it changed:

| Endpoint | Content |
| --- | --- |
| `/costmap/walk`, `/costmap/rover` | one byte per cell, size in `X-Width` / `X-Height` |
| `/route` | JSON list of `[x, y]` |
| `/points` | latest lidar scan in the `map` frame, float32 x y z, at most 20 000 points |
| `/camera/astronaut`, `/camera/rover` | latest camera frame as JPEG |

The dashboard has three tabs: a 3D map (Three.js) with the terrain, layers,
route, lidar points and markers; the two camera feeds with a HUD overlay on
the helmet camera; and the rover planner.

## Mission planner

`ros/mission_planner.py` plans a whole science EVA from `data/mission_boxwork.json`:
the objective (how the boxwork ridges formed), the crew rover parking point and
four targets with tasks, tools, time on site and priority. It subscribes to
`/costmap/walk`, `/costmap/rover`, `/nasa/dose_rate` and `/rover/config` and

- decides who works at each target: the astronaut, the rover arm (target in a
  keep-out cell or steeper than 15°; the astronaut stops at the nearest safe
  point) or with the crew rover (the core drill stays on the rover, so the rover
  must be able to drive there),
- orders the targets for the shortest walk (all orders are tried) and plans
  every leg with A* on the walking cost map,
- checks oxygen (8 h suit, 30 min reserve, spare tanks if the helper robot
  carries them) and drops the lowest-priority targets if it does not last,
- checks tools and the arm against the rover plan.

It publishes `/mission/plan` (JSON, latched) and `/mission/route` (`nav_msgs/Path`,
latched). `std_msgs/Empty` on `/mission/start` (the "Start mission walk"
button) republishes the mission route on `/route`, so the simulation walks it.

### Mission walk in the simulation

The simulation subscribes to `/mission/plan` and turns every target on the
route into a stop (`sim/mission_walk.py`):

- at an astronaut target the astronaut stands for the target's work time,
- at an arm target (too steep for the crew) the astronaut waits at the safe
  stop until the rover is within 7 m, then the arm runs its sample sequence:
  reach out, down to the ground, over the sample box, stow (arm commands from
  the dashboard are ignored while it runs),
- after the last target the astronaut walks back to the crew rover parking.

Work times are scaled for the demo: `--work-scale` simulated seconds per
minute of work (default 2), and `--walk-speed` sets the astronaut's pace
(default 0.8 m/s; the rover speeds up to keep pace, at most 2.5 m/s). Progress
goes out on `/mission/progress` (`std_msgs/String`, JSON: phase, target,
work time left, arm step) and shows in the Mission tab and the helmet HUD
overlay.

```bash
MISSION=data/mission_test.json ./scripts/run_dashboard.sh   # short 2-target mission; omit MISSION for Boxwork EVA 1
./scripts/run_sim.sh --walk-speed 1.2 --work-scale 1.0
./scripts/ros_shell.sh ros2 topic pub --once /mission/start std_msgs/msg/Empty "{}"
```

In the dashboard's Mission tab the mission can be switched without a restart
(the picker lists `data/mission_*.json` and sends the file name on
`/mission/select`, `std_msgs/String`), started with "Start mission walk", and
followed in the live banner and the mission log, one row per phase change in
simulation time.

Keep the walk at 1.2 m/s or below: the rover is capped at 1.5 m/s, faster it
leaves the route and tips over. The Jackal carries 45 kg of ballast low in the
chassis so the arm does not make it top-heavy. If it still tips over, or sits
stuck on one of the terrain model's 2 m steps for 5 s, the simulation puts it
back upright on the route and logs it.
The dashboard's Mission tab shows the plan; the 3D map shows numbered pins and
the mission route.

## Helmet HUD

`http://localhost:8080/app/hud.html` is the helmet view for the XREAL One
glasses: black background (transparent on the glasses), bright text only. It
reads the same WebSocket as the dashboard, nothing is sent back. It shows the
task now (from `/mission/progress`), an arrow and distance to the next target,
oxygen with the margin, the rover's distance and state, the dose, and a red
TURN BACK when `/suit/status` says so.

## Rover planner

The third tab picks one of the rovers in `app/rover_catalog.json` (pressurised
crew rover, open crew rover, helper robot), fits equipment with quantities and
checks payload, mount slots and battery endurance, with a 3D preview. All
catalogue numbers are concept values, not specifications. "Send to ROS 2"
publishes the plan as JSON on `/rover/config` (`std_msgs/String`, latched):

```json
{"rover": "crew_pressurised", "rover_name": "Pressurised crew rover",
 "equipment": {"arm_heavy": 1, "core_drill": 1, "o2_tank": 2},
 "payload_kg": 238, "equipment_power_w": 400, "drive_hours": 19.5,
 "range_km": 195.0, "extra_o2_hours": 4, "max_slope_deg": 15, "shelter": true}
```

Nothing subscribes to it yet; the cost map and the suit monitor could take the
rover's slope limit and the spare oxygen from it. Equipment shapes in the
preview are stand-ins for the team's CAD models.

# Marswalk Planner

NASA Space Apps Challenge 2026, Stalowa Wola. Challenge: *Interplanetary Survival Guide: Martian Map*.

A layered map and route planner for a crewed walk on Mars, built for the boxwork region on Mount Sharp (Gale crater). It merges data from several NASA missions into one small-area map, plans a route for a person in a spacesuit, and shows it on a habitat screen and on a helmet HUD (XREAL One glasses). A support rover with a robotic arm carries tools and reaches places the crew should not enter.

## Repository layout

| Folder | Contents | Owner |
| --- | --- | --- |
| `data/` | terrain patch (`terrain/`), derived layers (`layers/`), `meta.json`, routes; raw downloads stay local in `raw/` | Kuba |
| `sim/` | Isaac Sim scene, rover drive and terrain preparation scripts | Kuba |
| `app/` | web dashboard: map, layers, live positions | Kuba |
| `ros/` | ROS 2 nodes and the telemetry server for the browser | Rafał, Kuba |
| `planner/` | cost map and route planner | Rafał, Kuba |
| `scripts/` | launchers: simulation, dashboard, ROS 2 shell | Kuba |
| `docker/` | ROS 2 Humble image | Kuba |
| `media/` | slides, video, screenshots, CAD renders | Dominika, Wanessa, Gosia |
| `docs/` | challenge text, NASA resources, reports, team plan (in Polish) | all |

## Quick start

```bash
./scripts/run_dashboard.sh   # dashboard on http://localhost:8080
./scripts/run_sim.sh         # Isaac Sim, publishes to ROS 2
```

The simulation needs the raw HiRISE files in `data/raw/` and one run of
`sim/prepare_terrain.py` (`hires`) and `sim/build_scene.py`. The dashboard
works from the files already in `data/`.

## Shared conventions

- Coordinates: local metres, origin at the south-west corner of the terrain crop, x east, y north.
- Layers: `data/layers/*.npy` (values) and `*.png` (images), described in `data/meta.json`.
- Route: GeoJSON in local metres, for now `data/route_example.geojson`.
- ROS 2 topics: `ros/README.md`.
- Live telemetry for the browser: one JSON message over WebSocket, format in `docs/plan_dzialania.md`.

## Use of AI tools

Parts of the code, documentation and repository setup in this project were written with the help of an AI assistant (Claude, Anthropic). AI-assisted commits carry a `Co-Authored-By: Claude` trailer in their metadata.

## NASA data and resources

See `docs/nasa_data.md` and the data table in `docs/raport_marswalk_planner.md`.

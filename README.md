# Marswalk Planner

NASA Space Apps Challenge 2026, Stalowa Wola. Challenge: *Interplanetary Survival Guide: Martian Map*.

A layered map and route planner for a crewed walk on Mars, built for the boxwork region on Mount Sharp (Gale crater). It merges data from several NASA missions into one small-area map, plans a route for a person in a spacesuit, and shows it on a habitat screen and on a helmet HUD (XREAL One glasses). A support rover with a robotic arm carries tools and reaches places the crew should not enter.

## Repository layout

| Folder | Contents | Owner |
| --- | --- | --- |
| `data/` | terrain layers (`layers/`), `meta.json`, `route.geojson`; raw downloads stay local in `raw/` | Kuba |
| `planner/` | cost map and A* route planner | Rafał |
| `ros/` | ROS 2 nodes (suit sensors) and the WebSocket telemetry server | Rafał, Kuba |
| `sim/` | Isaac Sim scene and scripts | Kuba |
| `app/` | web app: habitat screen and HUD mode | Gosia |
| `media/` | slides, video, screenshots | Dominika, Wanessa |
| `docs/` | challenge text, NASA resources, reports, team plan (in Polish) | all |

## Shared conventions

- Coordinates: local metres, origin at the south-west corner of the terrain crop, x east, y north.
- Layers: PNG files with the same size as the DTM crop, described in `data/meta.json`.
- Route: `data/route.geojson`.
- Live telemetry: one JSON message over WebSocket, format in `docs/plan_dzialania.md`.

## NASA data and resources

See `docs/nasa_data.md` and the data table in `docs/raport_marswalk_planner.md`.

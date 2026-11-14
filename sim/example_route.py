"""Write an example walking/driving route into data/route_example.geojson.

A stand-in for the real planner in planner/: plain A* on a coarse slope grid,
so the simulation has something to follow. Coordinates are local metres
(see data/terrain/meta.json). Needs only numpy.
"""

import argparse
import heapq
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TERRAIN = ROOT / "data" / "terrain"

COARSE = 4  # plan on every 4th height sample, about 8 m
MAX_SLOPE_DEG = 15.0  # steeper cells are closed


def plan(slope, start, goal):
    """A* over 8-connected cells; cost is distance, inflated on slopes."""
    ny, nx = slope.shape
    open_set = [(0.0, start)]
    cost = {start: 0.0}
    parent = {}
    while open_set:
        _, cell = heapq.heappop(open_set)
        if cell == goal:
            path = [cell]
            while cell in parent:
                cell = parent[cell]
                path.append(cell)
            return path[::-1]
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nxt = (cell[0] + dy, cell[1] + dx)
                if nxt == cell or not (0 <= nxt[0] < ny and 0 <= nxt[1] < nx):
                    continue
                if slope[nxt] > MAX_SLOPE_DEG:
                    continue
                step = np.hypot(dy, dx) * (1.0 + slope[nxt] / MAX_SLOPE_DEG)
                new_cost = cost[cell] + step
                if new_cost < cost.get(nxt, np.inf):
                    cost[nxt] = new_cost
                    parent[nxt] = cell
                    heuristic = np.hypot(goal[0] - nxt[0], goal[1] - nxt[1])
                    heapq.heappush(open_set, (new_cost + heuristic, nxt))
    raise SystemExit("no route below the slope limit, pick other points")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", type=float, nargs=2, default=[1140.0, 830.0], metavar=("X", "Y"))
    parser.add_argument("--goal", type=float, nargs=2, default=[900.0, 650.0], metavar=("X", "Y"))
    args = parser.parse_args()

    meta = json.loads((TERRAIN / "meta.json").read_text())
    heights = np.load(TERRAIN / "heights.npy")[::COARSE, ::COARSE]
    cell = meta["cell_m"] * COARSE
    dz_dy, dz_dx = np.gradient(heights, cell)
    slope = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))

    to_cell = lambda p: (int(round(p[1] / cell)), int(round(p[0] / cell)))
    cells = plan(slope, to_cell(args.start), to_cell(args.goal))
    points = [[round(ix * cell, 2), round(iy * cell, 2), round(float(heights[iy, ix]), 2)] for iy, ix in cells]
    length = float(sum(np.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])))

    route = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {
                "name": "example route",
                "frame": meta["frame"],
                "length_m": round(length, 1),
                "max_slope_deg": round(float(max(slope[c] for c in cells)), 1),
            },
            "geometry": {"type": "LineString", "coordinates": points},
        }],
    }
    out = ROOT / "data" / "route_example.geojson"
    out.write_text(json.dumps(route) + "\n")
    print(f"{len(points)} points, {length:.0f} m, max slope {route['features'][0]['properties']['max_slope_deg']} deg -> {out}")

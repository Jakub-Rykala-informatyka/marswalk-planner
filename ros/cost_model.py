"""Cost model and route search shared by the ROS nodes and the slide scripts.

cost() turns slope, roughness and dose into a 0..100 cost per cell (costmap.py);
astar() finds the cheapest route over that cost (planner.py). Needs only numpy,
so it also runs outside ROS (sim/costmap_slide.py).
"""

import heapq
import math

import numpy as np

# variant: {parameter: default}. Assumptions to tune, not measured limits.
DEFAULTS = {
    # Walking in a suit: easy up to about 15 deg, forbidden from 25 deg
    "walk": {"max_slope_deg": 25.0, "comfort_slope_deg": 15.0, "slope_weight": 70.0,
             "max_roughness_m": 2.0, "roughness_weight": 15.0, "dose_weight": 10.0},
    # Pressurised rover: gentler slopes, no boulder fields, cabin shields the crew
    "rover": {"max_slope_deg": 15.0, "comfort_slope_deg": 8.0, "slope_weight": 70.0,
              "max_roughness_m": 1.0, "roughness_weight": 25.0, "dose_weight": 0.0},
}

NEIGHBOURS = [(dy, dx, math.hypot(dy, dx)) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]


def cost(slope_deg, roughness_m, dose_share, p):
    """Cost 0..100 per cell; dose_share is the dose rate as a share of open ground."""
    over = np.clip((slope_deg - p["comfort_slope_deg"]) / (p["max_slope_deg"] - p["comfort_slope_deg"]), 0, 1)
    gentle = np.clip(slope_deg / p["comfort_slope_deg"], 0, 1)
    value = (p["slope_weight"] * (0.2 * gentle + 0.8 * over ** 2)
             + p["roughness_weight"] * np.clip(roughness_m / p["max_roughness_m"], 0, 1)
             + p["dose_weight"] * dose_share)
    value = np.clip(np.rint(value), 0, 99)
    value[(slope_deg >= p["max_slope_deg"]) | (roughness_m >= p["max_roughness_m"])] = 100
    return value.astype(np.int8)


def coarsen(values, factor, reduce):
    """Merge factor x factor blocks; the edge that does not fill a block is dropped."""
    ny, nx = (s // factor for s in values.shape)
    blocks = values[:ny * factor, :nx * factor].reshape(ny, factor, nx, factor)
    return reduce(blocks, axis=(1, 3))


def nearest_free(cost, cell, radius=10):
    """The cell itself if it is passable, else the closest passable one nearby."""
    y, x = cell
    best = None
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            iy, ix = y + dy, x + dx
            if 0 <= iy < cost.shape[0] and 0 <= ix < cost.shape[1] and cost[iy, ix] < 100:
                d = math.hypot(dy, dx)
                if best is None or d < best[0]:
                    best = (d, (iy, ix))
    return best[1] if best else None


def astar(cost, start, goal, cost_scale):
    """Cheapest 8-connected path; a step costs its length times (1 + cost / cost_scale)."""
    ny, nx = cost.shape
    best = {start: 0.0}
    parent = {}
    frontier = [(0.0, start)]
    while frontier:
        _, cell = heapq.heappop(frontier)
        if cell == goal:
            path = [cell]
            while cell in parent:
                cell = parent[cell]
                path.append(cell)
            return path[::-1]
        base = best[cell]
        for dy, dx, length in NEIGHBOURS:
            iy, ix = cell[0] + dy, cell[1] + dx
            if not (0 <= iy < ny and 0 <= ix < nx):
                continue
            c = cost[iy, ix]
            if c >= 100:
                continue
            new = base + length * (1.0 + c / cost_scale)
            nxt = (iy, ix)
            if new < best.get(nxt, math.inf):
                best[nxt] = new
                parent[nxt] = cell
                heapq.heappush(frontier, (new + math.hypot(goal[0] - iy, goal[1] - ix), nxt))
    return None

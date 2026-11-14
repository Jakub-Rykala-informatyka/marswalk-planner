"""ROS 2 node that plans a whole science EVA: target order, who does what, and the budget.

Reads the mission (science objective and targets) from data/mission_boxwork.json
and subscribes to the cost maps, the dose-rate layer and the rover plan
(/rover/config). For every target it decides who does the work:

  astronaut   the target is on ground the crew may walk on
  arm         the target is in a keep-out cell or steeper than the comfortable
              slope; the astronaut stops at the nearest safe point and the
              rover's arm reaches in
  rover       a task needs equipment that stays on the rover (the core drill),
              so the crew rover must be able to drive to the target

It orders the targets to keep the walk short, plans each leg with A* on the
walking cost map, checks oxygen (with the 30 min reserve) and tools against the
rover plan, and drops the lowest-priority targets if the oxygen does not last.

Publishes /mission/plan (std_msgs/String, JSON, latched) and /mission/route
(nav_msgs/Path, latched). A message on /mission/start republishes the mission
route on /route, so the simulation walks it.
"""

import itertools
import json
import math
from pathlib import Path as FilePath

import numpy as np
import rclpy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import OccupancyGrid, Path
from rclpy.node import Node
from std_msgs.msg import Empty, String

from planner import LATCHED, astar, coarsen, grid_values, nearest_free

ROOT = FilePath(__file__).resolve().parents[1]
MISSION = ROOT / "data" / "mission_boxwork.json"
ARMS = ("arm_heavy", "arm_light")
ROVER_ONLY_TOOLS = ("core_drill",)  # too heavy to carry: the rover brings it


class MissionPlanner(Node):
    def __init__(self):
        super().__init__("mission_planner")
        self.declare_parameter("walk_speed", 0.8)  # m/s, as in the simulation
        self.declare_parameter("comfort_slope_deg", 15.0)  # steeper targets go to the arm
        self.declare_parameter("o2_hours", 8.0)  # suit endurance, as in suit_monitor
        self.declare_parameter("reserve_min", 30.0)
        self.declare_parameter("coarse", 2)
        self.declare_parameter("cost_scale", 25.0)
        self.declare_parameter("mission_file", str(MISSION))  # e.g. data/mission_test.json for a short check
        self.mission = json.loads(FilePath(self.get_parameter("mission_file").value).read_text())
        meta = json.loads((ROOT / "data" / "meta.json").read_text())
        self.full_dose = meta["dose_model"]["open_ground_uSv_per_h"]
        self.slope = np.load(ROOT / "data" / "layers" / "slope.npy")
        self.grids = {}
        self.config = None
        for topic, key in (("/costmap/walk", "walk"), ("/costmap/rover", "rover"), ("/nasa/dose_rate", "dose")):
            self.create_subscription(OccupancyGrid, topic, lambda msg, k=key: self.on_grid(k, msg), LATCHED)
        self.create_subscription(String, "/rover/config", self.on_config, LATCHED)
        self.create_subscription(Empty, "/mission/start", self.on_start, 10)
        self.plan_pub = self.create_publisher(String, "/mission/plan", LATCHED)
        self.route_pub = self.create_publisher(Path, "/mission/route", LATCHED)
        self.walk_route_pub = self.create_publisher(Path, "/route", LATCHED)
        self.route = None

    def on_grid(self, key, msg):
        self.grids[key] = (grid_values(msg), msg.info)
        self.replan()

    def on_config(self, msg):
        self.config = json.loads(msg.data)
        self.replan()

    def on_start(self, _msg):
        if self.route is not None:
            self.route.header.stamp = self.get_clock().now().to_msg()  # newer than any route the sim holds
            self.walk_route_pub.publish(self.route)
            self.get_logger().info("mission route sent to /route")

    # --- helpers ---------------------------------------------------------------
    def cell_of(self, info, x, y, factor=1):
        res = info.resolution * factor
        return int((y - info.origin.position.y) / res), int((x - info.origin.position.x) / res)

    def leg(self, cost, info, factor, a, b):
        """Walking path between two points: list of (x, y) and its length."""
        start = nearest_free(cost, self.cell_of(info, *a, factor))
        goal = nearest_free(cost, self.cell_of(info, *b, factor))
        cells = astar(cost, start, goal, self.get_parameter("cost_scale").value) if start and goal else None
        if cells is None:
            return None, math.inf
        res = info.resolution * factor
        points = [(info.origin.position.x + (c[1] + 0.5) * res, info.origin.position.y + (c[0] + 0.5) * res)
                  for c in cells]
        return points, sum(math.dist(p, q) for p, q in zip(points, points[1:]))

    def dose_along(self, points, speed):
        grid, info = self.grids["dose"]
        rates = grid.astype(np.float32) / 100.0 * self.full_dose
        total = 0.0
        for p, q in zip(points, points[1:]):
            iy, ix = self.cell_of(info, *q)
            total += float(rates[min(iy, rates.shape[0] - 1), min(ix, rates.shape[1] - 1)]) * math.dist(p, q) / speed / 3600
        return total

    # --- planning --------------------------------------------------------------
    def assess(self, target, walk, rover, equipment):
        """Who does the work at a target, where the astronaut stops, and warnings."""
        (wgrid, winfo), (rgrid, rinfo) = walk, rover
        iy, ix = self.cell_of(winfo, target["x"], target["y"])
        slope = float(self.slope[iy, ix])
        keep_out = wgrid[iy, ix] >= 100
        warnings = []
        executor = "astronaut"
        stop = (target["x"], target["y"])
        if keep_out or slope > self.get_parameter("comfort_slope_deg").value:
            executor = "arm"
            free = nearest_free(wgrid, (iy, ix), radius=15)
            if free:
                stop = (winfo.origin.position.x + (free[1] + 0.5) * winfo.resolution,
                        winfo.origin.position.y + (free[0] + 0.5) * winfo.resolution)
            if not any(equipment.get(a) for a in ARMS):
                warnings.append("needs a robotic arm on the rover")
        needs_rover = [t for t in target["tools"] if t in ROVER_ONLY_TOOLS]
        if needs_rover:
            executor += " + rover"
            riy, rix = self.cell_of(rinfo, target["x"], target["y"])
            if rgrid[riy, rix] >= 100:
                warnings.append("the crew rover cannot drive to this target")
        missing = [t for t in target["tools"] if not equipment.get(t)]
        if self.config is None:
            warnings.append("no rover plan received yet: tools not checked")
        elif missing:
            warnings.append("missing on the rover: " + ", ".join(missing))
        return {"executor": executor, "slope_deg": round(slope, 1), "stop": [round(v, 1) for v in stop],
                "reach_m": round(math.dist(stop, (target["x"], target["y"])), 1), "warnings": warnings}

    def replan(self):
        if not all(k in self.grids for k in ("walk", "rover", "dose")):
            return
        walk_grid, info = self.grids["walk"]
        factor = self.get_parameter("coarse").value
        cost = coarsen(walk_grid.astype(np.int16), factor, np.max)
        speed = self.get_parameter("walk_speed").value
        equipment = (self.config or {}).get("equipment", {})
        start = (self.mission["start"]["x"], self.mission["start"]["y"])

        targets = {t["id"]: dict(t, **self.assess(t, self.grids["walk"], self.grids["rover"], equipment))
                   for t in self.mission["targets"]}
        stops = {tid: tuple(t["stop"]) for tid, t in targets.items()}
        stops["start"] = start

        legs = {}  # every pair once: (path, length)
        for a, b in itertools.combinations(stops, 2):
            path, length = self.leg(cost, info, factor, stops[a], stops[b])
            legs[(a, b)] = (path, length)
            legs[(b, a)] = (path[::-1] if path else None, length)

        o2_minutes = self.get_parameter("o2_hours").value * 60
        if self.config and self.config.get("rover") == "helper_robot":
            o2_minutes += self.config.get("extra_o2_hours", 0) * 60  # spare tanks walk along
        usable = o2_minutes - self.get_parameter("reserve_min").value

        chosen = sorted(targets, key=lambda tid: targets[tid]["priority"])
        dropped = []
        while chosen:
            best = None
            for order in itertools.permutations(chosen):
                sequence = ["start", *order, "start"]
                length = sum(legs[(p, q)][1] for p, q in zip(sequence, sequence[1:]))
                if best is None or length < best[0]:
                    best = (length, sequence)
            total_length, sequence = best
            minutes = total_length / speed / 60 + sum(targets[t]["minutes"] for t in chosen)
            if total_length < math.inf and minutes <= usable:
                break
            dropped.append(chosen.pop())  # lowest priority goes first
        if not chosen:
            self.plan_pub.publish(String(data=json.dumps({"ok": False, "name": self.mission["name"]})))
            return

        clock = 0.0
        path_points = []
        timeline = []
        dose = 0.0
        for p, q in zip(sequence, sequence[1:]):
            points, length = legs[(p, q)]
            walk_min = length / speed / 60
            clock += walk_min
            dose += self.dose_along(points, speed)
            path_points += points if not path_points else points[1:]
            entry = {"from": p, "to": q, "length_m": round(length), "walk_min": round(walk_min, 1),
                     "arrive_min": round(clock, 1)}
            if q != "start":
                work = targets[q]["minutes"]
                giy, gix = self.cell_of(self.grids["dose"][1], *stops[q])
                dose += float(self.grids["dose"][0][giy, gix]) / 100 * self.full_dose * work / 60
                clock += work
                entry["work_min"] = work
            timeline.append(entry)

        plan = {
            "ok": True,
            "id": self.mission["id"],
            "name": self.mission["name"],
            "objective": self.mission["objective"],
            "background": self.mission["background"],
            "site_note": self.mission["site_note"],
            "start": self.mission["start"],
            "order": [t for t in sequence[1:-1]],
            "targets": [targets[t] for t in sequence[1:-1]],
            "dropped": [{"id": t, "name": targets[t]["name"]} for t in dropped],
            "timeline": timeline,
            "rover": (self.config or {}).get("rover_name"),
            "totals": {
                "walk_m": round(total_length),
                "eva_min": round(clock),
                "o2_usable_min": round(usable),
                "o2_margin_min": round(usable - clock),
                "dose_uSv": round(dose, 1),
            },
        }
        self.plan_pub.publish(String(data=json.dumps(plan)))

        route = Path()
        route.header.frame_id = "map"
        route.header.stamp = self.get_clock().now().to_msg()
        for x, y in path_points:
            pose = PoseStamped()
            pose.header = route.header
            pose.pose.position.x, pose.pose.position.y = float(x), float(y)
            pose.pose.orientation.w = 1.0
            route.poses.append(pose)
        self.route = route
        self.route_pub.publish(route)
        self.get_logger().info(f"mission: {' -> '.join(sequence)}, {total_length:.0f} m, {clock:.0f} min EVA, "
                               f"margin {usable - clock:.0f} min, dropped {dropped}")


def main():
    rclpy.init()
    rclpy.spin(MissionPlanner())


if __name__ == "__main__":
    main()

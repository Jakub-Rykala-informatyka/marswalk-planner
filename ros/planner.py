"""ROS 2 node that plans the walking route with A* on the cost map.

Subscribes to /costmap/walk and /nasa/dose_rate (latched), /astronaut/pose and
/goal_pose. Publishes the route on /route (nav_msgs/Path, latched) and a short
budget on /route/summary (std_msgs/String with JSON): length, walking time,
radiation dose and the steepest cost on the way.

Plans when it starts (from the start and goal parameters), when a new goal
arrives (from the astronaut's current position) and when the cost map changes.
"""

import heapq
import json
import math
from pathlib import Path as FilePath

import numpy as np
import rclpy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import OccupancyGrid, Path
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

ROOT = FilePath(__file__).resolve().parents[1]
LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                     reliability=ReliabilityPolicy.RELIABLE)
NEIGHBOURS = [(dy, dx, math.hypot(dy, dx)) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]


def grid_values(msg):
    data = np.frombuffer(bytes(np.array(msg.data, dtype=np.int8)), dtype=np.int8)
    return data.reshape(msg.info.height, msg.info.width)


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


class Planner(Node):
    def __init__(self):
        super().__init__("planner")
        # Defaults: the ends of data/route_example.geojson, in local metres
        self.declare_parameter("start_x", 1141.0)
        self.declare_parameter("start_y", 834.0)
        self.declare_parameter("goal_x", 898.0)
        self.declare_parameter("goal_y", 648.0)
        self.declare_parameter("coarse", 2)  # plan on 2 x 2 blocks of the cost map, about 4 m
        self.declare_parameter("cost_scale", 25.0)  # cost 25 doubles the price of a step
        self.declare_parameter("walk_speed", 0.8)  # m/s, the same pace as the simulation
        self.costmap = None
        self.dose = None
        self.astronaut = None
        self.goal = (self.get_parameter("goal_x").value, self.get_parameter("goal_y").value)
        self.create_subscription(OccupancyGrid, "/costmap/walk", self.on_costmap, LATCHED)
        self.create_subscription(OccupancyGrid, "/nasa/dose_rate", self.on_dose, LATCHED)
        self.create_subscription(PoseStamped, "/astronaut/pose", self.on_astronaut, 10)
        self.create_subscription(PoseStamped, "/goal_pose", self.on_goal, 10)
        self.route_pub = self.create_publisher(Path, "/route", LATCHED)
        self.summary_pub = self.create_publisher(String, "/route/summary", LATCHED)
        meta = json.loads((ROOT / "data" / "meta.json").read_text())
        self.full_dose = meta["dose_model"]["open_ground_uSv_per_h"]

    def on_costmap(self, msg):
        self.costmap = msg
        self.plan(self.astronaut or self.start_param())

    def on_dose(self, msg):
        self.dose = grid_values(msg).astype(np.float32) / 100.0 * self.full_dose

    def on_astronaut(self, msg):
        self.astronaut = (msg.pose.position.x, msg.pose.position.y)

    def on_goal(self, msg):
        self.goal = (msg.pose.position.x, msg.pose.position.y)
        self.plan(self.astronaut or self.start_param())

    def start_param(self):
        return (self.get_parameter("start_x").value, self.get_parameter("start_y").value)

    def plan(self, start_xy):
        if self.costmap is None:
            return
        info = self.costmap.info
        factor = self.get_parameter("coarse").value
        res = info.resolution
        cost = coarsen(grid_values(self.costmap).astype(np.int16), factor, np.max)
        to_cell = lambda p: (int((p[1] - info.origin.position.y) / (res * factor)),
                             int((p[0] - info.origin.position.x) / (res * factor)))
        to_xy = lambda c: (info.origin.position.x + (c[1] + 0.5) * res * factor,
                           info.origin.position.y + (c[0] + 0.5) * res * factor)

        start, goal = nearest_free(cost, to_cell(start_xy)), nearest_free(cost, to_cell(self.goal))
        cells = astar(cost, start, goal, self.get_parameter("cost_scale").value) if start and goal else None
        if cells is None:
            self.get_logger().warn(f"no route from {start_xy} to {self.goal}")
            self.summary_pub.publish(String(data=json.dumps({"ok": False, "goal": self.goal})))
            return

        points = [start_xy] + [to_xy(c) for c in cells[1:-1]] + [to_xy(cells[-1])]
        path = Path()
        path.header.frame_id = "map"
        path.header.stamp = self.get_clock().now().to_msg()
        for x, y in points:
            pose = PoseStamped()
            pose.header = path.header
            pose.pose.position.x, pose.pose.position.y = float(x), float(y)
            pose.pose.orientation.w = 1.0
            path.poses.append(pose)
        self.route_pub.publish(path)

        steps = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])]
        length = sum(steps)
        speed = self.get_parameter("walk_speed").value
        dose = 0.0
        if self.dose is not None:
            for (x, y), step in zip(points[1:], steps):
                iy = min(int((y - info.origin.position.y) / res), self.dose.shape[0] - 1)
                ix = min(int((x - info.origin.position.x) / res), self.dose.shape[1] - 1)
                dose += float(self.dose[iy, ix]) * step / speed / 3600.0
        summary = {
            "ok": True,
            "goal": [round(v, 1) for v in self.goal],
            "length_m": round(length, 1),
            "walk_time_s": round(length / speed),
            "dose_uSv": round(dose, 2),
            "max_cost": int(max(cost[c] for c in cells)),
        }
        self.summary_pub.publish(String(data=json.dumps(summary)))
        self.get_logger().info(f"route {length:.0f} m, {length / speed / 60:.1f} min, {dose:.2f} uSv")


def main():
    rclpy.init()
    rclpy.spin(Planner())


if __name__ == "__main__":
    main()

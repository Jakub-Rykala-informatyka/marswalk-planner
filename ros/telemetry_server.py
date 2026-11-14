"""ROS 2 node that serves the dashboard and streams telemetry to it over WebSocket.

Subscribes to the simulation topics (see ros/README.md), keeps the latest value
of each, and sends one JSON message to every browser a few times per second.
Also serves the app/ and data/ folders, so the dashboard is one address:
http://localhost:8080
"""

import argparse
import asyncio
import io
import json
import math
import threading
from pathlib import Path

import numpy as np
import rclpy
from aiohttp import WSMsgType, web
from PIL import Image as PilImage
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import OccupancyGrid, Path as RoutePath
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import Image, PointCloud2
from std_msgs.msg import Float32, String

ROOT = Path(__file__).resolve().parents[1]
STALE_AFTER = 2.0  # s without a pose before the dashboard shows the source as offline
COSTMAPS = ("walk", "rover")
CAMERAS = {"astronaut": "/astronaut/camera/image", "rover": "/rover/camera/image"}
LIDAR_HEIGHT = 0.45  # m, lidar above the rover pose (sim/sensors.py)
MAX_POINTS = 20000  # points sent to the browser per scan
LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                     reliability=ReliabilityPolicy.RELIABLE)


def pose_dict(msg):
    q = msg.pose.orientation
    yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
    p = msg.pose.position
    return {"x": round(p.x, 2), "y": round(p.y, 2), "z": round(p.z, 2),
            "heading_deg": round(math.degrees(yaw), 1)}


class Telemetry(Node):
    """Latest value of every topic, read by the web thread."""

    def __init__(self):
        super().__init__("marswalk_telemetry")
        self.sim_time = None
        self.astronaut = None
        self.rover = None
        self.rover_state = None
        self.dose_rate = None
        self.dose = None
        self.last_pose_wall = 0.0
        self.costmaps = {}  # variant: (version, width, height, cell bytes)
        self.route = (0, [])  # version, [[x, y], ...]
        self.route_summary = None
        self.suit_status = None
        self.rover_pose = None  # position and rotation matrix, for the lidar
        self.points = (0, b"")  # version, float32 x y z in the map frame
        self.images = {}  # camera: (version, ros Image)
        self.create_subscription(PointCloud2, "/rover/points", self.on_points, 2)
        for name, topic in CAMERAS.items():
            self.create_subscription(Image, topic, lambda msg, n=name: self.on_image(n, msg), 2)
        self.create_subscription(String, "/suit/status", self.on_suit_status, 10)
        self.goal_pub = self.create_publisher(PoseStamped, "/goal_pose", 10)
        self.config_pub = self.create_publisher(String, "/rover/config", LATCHED)
        self.create_subscription(RoutePath, "/route", self.on_route, LATCHED)
        self.create_subscription(String, "/route/summary", self.on_route_summary, LATCHED)
        self.create_subscription(Clock, "/clock", self.on_clock, 10)
        self.create_subscription(PoseStamped, "/astronaut/pose", self.on_astronaut, 10)
        self.create_subscription(PoseStamped, "/rover/pose", self.on_rover, 10)
        self.create_subscription(String, "/rover/state", self.on_rover_state, 10)
        self.create_subscription(Float32, "/astronaut/dose_rate", self.on_dose_rate, 10)
        self.create_subscription(Float32, "/astronaut/dose", self.on_dose, 10)
        for variant in COSTMAPS:
            self.create_subscription(OccupancyGrid, f"/costmap/{variant}",
                                     lambda msg, v=variant: self.on_costmap(v, msg), LATCHED)

    def on_clock(self, msg):
        self.sim_time = msg.clock.sec + msg.clock.nanosec * 1e-9

    def on_astronaut(self, msg):
        self.astronaut = pose_dict(msg)
        self.last_pose_wall = self.get_clock().now().nanoseconds * 1e-9

    def on_rover(self, msg):
        self.rover = pose_dict(msg)
        q, p = msg.pose.orientation, msg.pose.position
        w, x, y, z = q.w, q.x, q.y, q.z
        rotation = np.array([
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ])
        self.rover_pose = (np.array([p.x, p.y, p.z]), rotation)

    def on_points(self, msg):
        """Lidar scan in the sensor frame, moved into the map frame with the latest rover pose."""
        if self.rover_pose is None or msg.width * msg.height == 0:
            return
        offsets = {f.name: f.offset for f in msg.fields}
        raw = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(-1, msg.point_step)
        xyz = np.stack([raw[:, offsets[k]:offsets[k] + 4].copy().view(np.float32)[:, 0] for k in "xyz"], axis=1)
        xyz = xyz[np.isfinite(xyz).all(axis=1)]
        if len(xyz) > MAX_POINTS:
            xyz = xyz[np.linspace(0, len(xyz) - 1, MAX_POINTS).astype(int)]
        position, rotation = self.rover_pose
        world = (xyz + [0.0, 0.0, LIDAR_HEIGHT]) @ rotation.T + position
        self.points = (self.points[0] + 1, world.astype(np.float32).tobytes())

    def on_image(self, name, msg):
        version = self.images.get(name, (0,))[0] + 1
        self.images[name] = (version, msg)

    def on_rover_state(self, msg):
        self.rover_state = msg.data

    def on_dose_rate(self, msg):
        self.dose_rate = msg.data

    def on_dose(self, msg):
        self.dose = msg.data

    def on_costmap(self, variant, msg):
        version = self.costmaps.get(variant, (0,))[0] + 1
        cells = bytes(array_bytes(msg.data))
        self.costmaps[variant] = (version, msg.info.width, msg.info.height, cells)

    def on_route(self, msg):
        points = [[round(p.pose.position.x, 2), round(p.pose.position.y, 2)] for p in msg.poses]
        self.route = (self.route[0] + 1, points)

    def on_suit_status(self, msg):
        self.suit_status = json.loads(msg.data)

    def on_route_summary(self, msg):
        self.route_summary = json.loads(msg.data)

    def publish_goal(self, x, y):
        msg = PoseStamped()
        msg.header.frame_id = "map"
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.pose.position.x, msg.pose.position.y = float(x), float(y)
        msg.pose.orientation.w = 1.0
        self.goal_pub.publish(msg)

    def snapshot(self):
        age = self.get_clock().now().nanoseconds * 1e-9 - self.last_pose_wall
        live = self.astronaut is not None and age < STALE_AFTER
        message = {"live": live, "t": self.sim_time, "astronaut": self.astronaut, "rover": None,
                   "costmaps": {variant: entry[0] for variant, entry in self.costmaps.items()},
                   "route": {"version": self.route[0], "summary": self.route_summary},
                   "points": self.points[0],
                   "cameras": {name: entry[0] for name, entry in self.images.items()}}
        suit = dict(self.suit_status or {})
        if self.dose_rate is not None:
            suit.update(dose_rate_uSv_h=round(self.dose_rate, 2), dose_uSv=round(self.dose, 3))
        if suit:
            message["suit"] = suit
        if self.rover:
            message["rover"] = {**self.rover, "state": self.rover_state}
        if self.rover and self.astronaut:
            message["rover_distance_m"] = round(
                math.hypot(self.rover["x"] - self.astronaut["x"], self.rover["y"] - self.astronaut["y"]), 1)
        return message


def array_bytes(data):
    """OccupancyGrid data as raw bytes, whether rclpy gives an array or a list."""
    return data.tobytes() if hasattr(data, "tobytes") else bytes(v & 0xFF for v in data)


async def points(request):
    """Latest lidar scan: float32 x, y, z per point in the map frame."""
    return web.Response(body=request.app["telemetry"].points[1], content_type="application/octet-stream",
                        headers={"Cache-Control": "no-store"})


def to_jpeg(msg):
    channels = {"rgb8": 3, "rgba8": 4, "bgr8": 3, "bgra8": 4}[msg.encoding]
    pixels = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(msg.height, msg.step)
    pixels = pixels[:, :msg.width * channels].reshape(msg.height, msg.width, channels)[:, :, :3]
    if msg.encoding.startswith("bgr"):
        pixels = pixels[:, :, ::-1]
    out = io.BytesIO()
    PilImage.fromarray(pixels).save(out, format="JPEG", quality=80)
    return out.getvalue()


async def camera(request):
    """Latest frame of a camera as JPEG."""
    entry = request.app["telemetry"].images.get(request.match_info["name"])
    if entry is None:
        raise web.HTTPNotFound()
    body = await asyncio.get_running_loop().run_in_executor(None, to_jpeg, entry[1])
    return web.Response(body=body, content_type="image/jpeg", headers={"Cache-Control": "no-store"})


async def route(request):
    return web.json_response(request.app["telemetry"].route[1], headers={"Cache-Control": "no-store"})


async def costmap(request):
    """Raw cost map cells, one byte each, row 0 at the south edge."""
    entry = request.app["telemetry"].costmaps.get(request.match_info["variant"])
    if entry is None:
        raise web.HTTPNotFound()
    _, width, height, cells = entry
    return web.Response(body=cells, content_type="application/octet-stream",
                        headers={"X-Width": str(width), "X-Height": str(height), "Cache-Control": "no-store"})


async def websocket(request):
    ws = web.WebSocketResponse(heartbeat=10.0)
    await ws.prepare(request)
    request.app["clients"].add(ws)
    try:
        async for msg in ws:
            if msg.type == WSMsgType.ERROR:
                break
            if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("goal"):  # a click on the map sets a new science target
                    request.app["telemetry"].publish_goal(data["goal"]["x"], data["goal"]["y"])
                if data.get("rover_config"):  # the rover planner tab
                    request.app["telemetry"].config_pub.publish(String(data=json.dumps(data["rover_config"])))
    finally:
        request.app["clients"].discard(ws)
    return ws


async def broadcast(app):
    period = 1.0 / app["rate"]
    while True:
        text = json.dumps(app["telemetry"].snapshot())
        for ws in list(app["clients"]):
            try:
                await ws.send_str(text)
            except ConnectionError:
                app["clients"].discard(ws)
        await asyncio.sleep(period)


async def start_broadcast(app):
    app["broadcast"] = asyncio.create_task(broadcast(app))


async def index(request):
    return web.FileResponse(ROOT / "app" / "index.html")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--rate", type=float, default=5.0, help="WebSocket messages per second")
    args = parser.parse_args()

    rclpy.init()
    telemetry = Telemetry()
    threading.Thread(target=rclpy.spin, args=(telemetry,), daemon=True).start()

    app = web.Application()
    app["telemetry"] = telemetry
    app["clients"] = set()
    app["rate"] = args.rate
    app.on_startup.append(start_broadcast)
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket)
    app.router.add_get("/costmap/{variant}", costmap)
    app.router.add_get("/route", route)
    app.router.add_get("/points", points)
    app.router.add_get("/camera/{name}", camera)
    app.router.add_static("/app", ROOT / "app")
    app.router.add_static("/data", ROOT / "data")
    web.run_app(app, port=args.port, print=lambda *_: print(f"dashboard on http://localhost:{args.port}"))


if __name__ == "__main__":
    main()

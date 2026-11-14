"""ROS 2 node that serves the dashboard and streams telemetry to it over WebSocket.

Subscribes to the simulation topics (see ros/README.md), keeps the latest value
of each, and sends one JSON message to every browser a few times per second.
Also serves the app/ and data/ folders, so the dashboard is one address:
http://localhost:8080
"""

import argparse
import asyncio
import json
import math
import threading
from pathlib import Path

import rclpy
from aiohttp import WSMsgType, web
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from std_msgs.msg import Float32, String

ROOT = Path(__file__).resolve().parents[1]
STALE_AFTER = 2.0  # s without a pose before the dashboard shows the source as offline


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
        self.create_subscription(Clock, "/clock", self.on_clock, 10)
        self.create_subscription(PoseStamped, "/astronaut/pose", self.on_astronaut, 10)
        self.create_subscription(PoseStamped, "/rover/pose", self.on_rover, 10)
        self.create_subscription(String, "/rover/state", self.on_rover_state, 10)
        self.create_subscription(Float32, "/astronaut/dose_rate", self.on_dose_rate, 10)
        self.create_subscription(Float32, "/astronaut/dose", self.on_dose, 10)

    def on_clock(self, msg):
        self.sim_time = msg.clock.sec + msg.clock.nanosec * 1e-9

    def on_astronaut(self, msg):
        self.astronaut = pose_dict(msg)
        self.last_pose_wall = self.get_clock().now().nanoseconds * 1e-9

    def on_rover(self, msg):
        self.rover = pose_dict(msg)

    def on_rover_state(self, msg):
        self.rover_state = msg.data

    def on_dose_rate(self, msg):
        self.dose_rate = msg.data

    def on_dose(self, msg):
        self.dose = msg.data

    def snapshot(self):
        age = self.get_clock().now().nanoseconds * 1e-9 - self.last_pose_wall
        live = self.astronaut is not None and age < STALE_AFTER
        message = {"live": live, "t": self.sim_time, "astronaut": self.astronaut, "rover": None}
        if self.dose_rate is not None:
            message["suit"] = {"dose_rate_uSv_h": round(self.dose_rate, 2), "dose_uSv": round(self.dose, 3)}
        if self.rover:
            message["rover"] = {**self.rover, "state": self.rover_state}
        if self.rover and self.astronaut:
            message["rover_distance_m"] = round(
                math.hypot(self.rover["x"] - self.astronaut["x"], self.rover["y"] - self.astronaut["y"]), 1)
        return message


async def websocket(request):
    ws = web.WebSocketResponse(heartbeat=10.0)
    await ws.prepare(request)
    request.app["clients"].add(ws)
    try:
        async for msg in ws:
            if msg.type == WSMsgType.ERROR:
                break
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
    app.router.add_static("/app", ROOT / "app")
    app.router.add_static("/data", ROOT / "data")
    web.run_app(app, port=args.port, print=lambda *_: print(f"dashboard on http://localhost:{args.port}"))


if __name__ == "__main__":
    main()

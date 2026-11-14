"""Simulate a Marswalk: an astronaut walks a route and the support rover follows.

Run with Isaac Sim's python.sh after build_scene.py, or through
scripts/run_sim.sh, which sets the ROS 2 environment for --ros.

The astronaut is a marker moved along the route at walking pace. The rover is
the Clearpath Jackal from the Isaac Sim asset library, driven with physics.
With --ros both poses are published to ROS 2 (topics in ros/README.md) and the
route comes from the planner on /route; a new route redirects the walk from
where the astronaut stands.
"""

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--route", default="data/route_example.geojson",
                    help="relative to the repo root; with --ros only used if /route stays silent")
parser.add_argument("--headless", action="store_true", help="run without the Isaac Sim window")
parser.add_argument("--ros", action="store_true", help="publish poses to ROS 2")
parser.add_argument("--camera", choices=("rover", "astronaut"), default="rover", help="what the view follows")
parser.add_argument("--record", action="store_true", help="save camera frames to media/frames/")
parser.add_argument("--capture-fps", type=float, default=10.0, help="frames and ROS messages per simulated second")
parser.add_argument("--max-time", type=float, default=900.0, help="stop after this many simulated seconds")
args = parser.parse_args()

from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": args.headless, "width": 1280, "height": 720})

from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.utils.extensions import enable_extension
from isaacsim.core.utils.stage import add_reference_to_stage, open_stage
from isaacsim.core.utils.types import ArticulationAction
from isaacsim.storage.native import get_assets_root_path
from omni.kit.viewport.utility import get_active_viewport
from pxr import Gf, UsdGeom

ROOT = Path(__file__).resolve().parents[1]
TERRAIN = ROOT / "data" / "terrain"
USD_PATH = TERRAIN / "mars_gale.usd"
FRAMES = ROOT / "media" / "frames"
LOG_PATH = ROOT / "data" / "preview" / "rover_log.csv"

MARS_GRAVITY = 3.72  # m/s^2
PHYSICS_DT = 1.0 / 60.0
# Jackal geometry, read from the asset
WHEEL_RADIUS = 0.098
CRUISE_SPEED = 1.5  # m/s
LOOKAHEAD = 2.5  # m, pure-pursuit distance
STEER_GAIN = 2.0  # m/s of wheel-speed difference per radian of heading error
SETTLE_STEPS = 30  # let the rover land on the ground before driving
RENDER_EVERY = 3  # physics steps per drawn frame in the window, 20 fps

WALK_SPEED = 0.8  # m/s, assumed pace in a suit on easy ground
ASTRONAUT_HEIGHT = 1.8  # m
EYE_HEIGHT = 1.7  # m
HEAD_START = 5.0  # m of route between rover and astronaut at the start
FOLLOW_GAP = 4.0  # m the rover keeps behind the astronaut
ROUTE_WAIT = 20.0  # s to wait for the planner's /route at start-up


class Route:
    """A polyline in local metres, addressed by distance walked along it."""

    def __init__(self, xy):
        self.xy = np.asarray(xy, dtype=float)[:, :2]
        self.arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(self.xy, axis=0), axis=1))])
        self.length = float(self.arc[-1])

    @classmethod
    def from_file(cls, path):
        feature = json.loads((ROOT / path).read_text())["features"][0]
        return cls(feature["geometry"]["coordinates"])

    def point(self, s):
        return np.array([np.interp(s, self.arc, self.xy[:, 0]), np.interp(s, self.arc, self.xy[:, 1])])

    def heading(self, s):
        ahead = self.point(min(s + 1.0, self.length)) - self.point(max(s - 1.0, 0.0))
        return math.atan2(ahead[1], ahead[0])

    def advance(self, s, position_xy, window=6.0):
        """Distance along the route closest to a position, never going backwards."""
        candidates = np.arange(s, min(s + window, self.length) + 0.01, 0.25)
        gaps = [np.linalg.norm(self.point(c) - position_xy) for c in candidates]
        return float(candidates[int(np.argmin(gaps))])


def ground_height(heights, cell, x, y):
    """Bilinear height of the terrain grid at a local position."""
    fx, fy = x / cell, y / cell
    ix, iy = int(fx), int(fy)
    tx, ty = fx - ix, fy - iy
    patch = heights[iy:iy + 2, ix:ix + 2]
    return float(patch[0, 0] * (1 - tx) * (1 - ty) + patch[0, 1] * tx * (1 - ty)
                 + patch[1, 0] * (1 - tx) * ty + patch[1, 1] * tx * ty)


def yaw_of(quat_wxyz):
    w, x, y, z = quat_wxyz
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def set_camera(camera_op, eye, target):
    view = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1))
    camera_op.Set(view.GetInverse())


class RosPublisher:
    """Poses in the `map` frame, which is the local frame of data/terrain/meta.json."""

    def __init__(self):
        enable_extension("isaacsim.ros2.bridge")
        simulation_app.update()
        import rclpy
        from geometry_msgs.msg import PoseStamped
        from nav_msgs.msg import Path
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from rosgraph_msgs.msg import Clock
        from std_msgs.msg import String

        self._types = PoseStamped, Clock, String
        rclpy.init()
        self._rclpy = rclpy
        self.node = rclpy.create_node("marswalk_sim")
        self.clock = self.node.create_publisher(Clock, "/clock", 10)
        self.astronaut = self.node.create_publisher(PoseStamped, "/astronaut/pose", 10)
        self.rover = self.node.create_publisher(PoseStamped, "/rover/pose", 10)
        self.rover_state = self.node.create_publisher(String, "/rover/state", 10)
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             reliability=ReliabilityPolicy.RELIABLE)
        self.new_route = None
        self.node.create_subscription(Path, "/route", self._on_route, latched)

    def _on_route(self, msg):
        points = [(p.pose.position.x, p.pose.position.y) for p in msg.poses]
        if len(points) > 1:
            self.new_route = points

    def poll_route(self):
        """Route points if a new route arrived since the last call, else None."""
        self._rclpy.spin_once(self.node, timeout_sec=0.0)
        points, self.new_route = self.new_route, None
        return points

    def wait_for_route(self, seconds):
        for _ in range(int(seconds * 10)):
            self._rclpy.spin_once(self.node, timeout_sec=0.1)
            if self.new_route:
                return self.poll_route()
        return None

    def _pose(self, stamp, position, yaw):
        PoseStamped = self._types[0]
        msg = PoseStamped()
        msg.header.stamp = stamp
        msg.header.frame_id = "map"
        msg.pose.position.x, msg.pose.position.y, msg.pose.position.z = (float(v) for v in position)
        msg.pose.orientation.z = math.sin(yaw / 2)
        msg.pose.orientation.w = math.cos(yaw / 2)
        return msg

    def publish(self, t, astronaut_position, astronaut_yaw, rover_position, rover_yaw, state):
        _, Clock, String = self._types
        clock = Clock()
        clock.clock.sec = int(t)
        clock.clock.nanosec = int((t - int(t)) * 1e9)
        self.clock.publish(clock)
        self.astronaut.publish(self._pose(clock.clock, astronaut_position, astronaut_yaw))
        self.rover.publish(self._pose(clock.clock, rover_position, rover_yaw))
        self.rover_state.publish(String(data=state))

    def close(self):
        self.node.destroy_node()
        self._rclpy.shutdown()


ros = RosPublisher() if args.ros else None
planned = ros.wait_for_route(ROUTE_WAIT) if ros else None
route = Route(planned) if planned else Route.from_file(args.route)
print(f"route: {'/route from the planner' if planned else args.route}, {route.length:.0f} m")
meta = json.loads((TERRAIN / "meta.json").read_text())
heights = np.load(TERRAIN / "heights.npy")
cell = meta["cell_m"]
start = route.point(0.0)
start_yaw = route.heading(0.0)

open_stage(str(USD_PATH))
world = World(physics_dt=PHYSICS_DT, rendering_dt=PHYSICS_DT, stage_units_in_meters=1.0)
world.get_physics_context().set_gravity(-MARS_GRAVITY)

add_reference_to_stage(get_assets_root_path() + "/Isaac/Robots/Clearpath/Jackal/jackal.usd", "/World/Rover")
rover = SingleArticulation(
    "/World/Rover", name="rover",
    position=np.array([start[0], start[1], ground_height(heights, cell, *start) + 0.2]),
    orientation=np.array([math.cos(start_yaw / 2), 0.0, 0.0, math.sin(start_yaw / 2)]),
)
world.scene.add(rover)

# Astronaut marker: no physics, placed on the terrain every step
astronaut = UsdGeom.Capsule.Define(world.stage, "/World/Astronaut")
astronaut.CreateRadiusAttr(0.28)
astronaut.CreateHeightAttr(ASTRONAUT_HEIGHT - 0.56)
astronaut.CreateAxisAttr("Z")
astronaut.CreateDisplayColorAttr([Gf.Vec3f(0.92, 0.92, 0.90)])
astronaut_op = UsdGeom.Xformable(astronaut).AddTranslateOp()

camera = UsdGeom.Camera.Define(world.stage, "/World/Cameras/Follow")
camera.CreateFocalLengthAttr(18.0)
camera.CreateClippingRangeAttr(Gf.Vec2f(0.05, 20000.0))
camera_op = UsdGeom.Xformable(camera).AddTransformOp()
if not args.headless:
    get_active_viewport().camera_path = "/World/Cameras/Follow"

world.reset()
left = [i for i, name in enumerate(rover.dof_names) if "left" in name]
right = [i for i, name in enumerate(rover.dof_names) if "right" in name]

annotator = None
if args.record:
    import omni.replicator.core as rep
    from PIL import Image

    FRAMES.mkdir(parents=True, exist_ok=True)
    for old in FRAMES.glob("frame_*.jpg"):
        old.unlink()
    rep.orchestrator.set_capture_on_play(False)
    product = rep.create.render_product("/World/Cameras/Follow", (1280, 720))
    annotator = rep.AnnotatorRegistry.get_annotator("rgb")
    annotator.attach([product])

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
log_file = LOG_PATH.open("w", newline="")
log = csv.writer(log_file)
log.writerow(["t", "astronaut_x", "astronaut_y", "rover_x", "rover_y", "rover_z", "rover_yaw_deg", "gap_m", "state"])

steps_per_frame = max(1, round(1.0 / (args.capture_fps * PHYSICS_DT)))
rover_s, frame, step = 0.0, 0, 0
state = "following"
walk_start, head_start = SETTLE_STEPS * PHYSICS_DT, HEAD_START
while simulation_app.is_running() and step * PHYSICS_DT < args.max_time:
    t = step * PHYSICS_DT
    points = ros.poll_route() if ros else None
    if points:  # new route from the planner: it starts where the astronaut stands
        route = Route(points)
        walk_start, head_start, rover_s = t, 0.0, 0.0
        print(f"t={t:.0f} s: new route, {route.length:.0f} m")
    astronaut_s = min(head_start + WALK_SPEED * max(0.0, t - walk_start), route.length)
    astronaut_xy = route.point(astronaut_s)
    astronaut_z = ground_height(heights, cell, *astronaut_xy)
    astronaut_yaw = route.heading(astronaut_s)
    astronaut_op.Set(Gf.Vec3d(astronaut_xy[0], astronaut_xy[1], astronaut_z + ASTRONAUT_HEIGHT / 2))

    position, orientation = rover.get_world_pose()
    yaw = yaw_of(orientation)
    rover_s = route.advance(rover_s, position[:2])
    room = astronaut_s - FOLLOW_GAP - rover_s  # how far the rover may still drive
    if room <= 0.0:
        state = "arrived" if astronaut_s >= route.length else "waiting"
        if state == "arrived" and not ros:
            break  # with ROS keep running: a new goal can start another walk
        speed = skid = 0.0
    else:
        state = "following"
        to_target = route.point(rover_s + min(LOOKAHEAD, room + 0.5)) - position[:2]
        heading_error = math.atan2(to_target[1], to_target[0]) - yaw
        heading_error = math.atan2(math.sin(heading_error), math.cos(heading_error))
        # Skid steering scrubs sideways, so the turn is a wheel-speed difference
        # proportional to the heading error, not the ideal differential-drive formula
        speed = min(CRUISE_SPEED, 0.8 * room + 0.2) * max(0.0, math.cos(heading_error)) ** 2
        skid = float(np.clip(STEER_GAIN * heading_error, -CRUISE_SPEED, CRUISE_SPEED))
    if step < SETTLE_STEPS:
        speed = skid = 0.0

    velocities = np.zeros(rover.num_dof)
    velocities[left] = (speed - skid) / WHEEL_RADIUS
    velocities[right] = (speed + skid) / WHEEL_RADIUS
    rover.apply_action(ArticulationAction(joint_velocities=velocities))

    capture = step % steps_per_frame == 0
    if capture:
        if args.camera == "astronaut":
            forward = np.array([math.cos(astronaut_yaw), math.sin(astronaut_yaw), 0.0])
            eye = np.array([*astronaut_xy, astronaut_z + EYE_HEIGHT]) + 0.4 * forward
            set_camera(camera_op, eye, eye + 10.0 * forward - np.array([0.0, 0.0, 1.0]))
        else:
            forward = np.array([math.cos(yaw), math.sin(yaw), 0.0])
            set_camera(camera_op, position - 3.0 * forward + np.array([0.0, 0.0, 1.3]),
                       position + 4.0 * forward + np.array([0.0, 0.0, 0.3]))
        if ros:
            ros.publish(t, (*astronaut_xy, astronaut_z), astronaut_yaw, position, yaw, state)
        log.writerow([f"{t:.2f}", f"{astronaut_xy[0]:.2f}", f"{astronaut_xy[1]:.2f}",
                      f"{position[0]:.2f}", f"{position[1]:.2f}", f"{position[2]:.2f}",
                      f"{math.degrees(yaw):.1f}", f"{astronaut_s - rover_s:.1f}", state])
        log_file.flush()
    # Rendering every physics step would slow the window well below real time
    show = not args.headless and step % RENDER_EVERY == 0
    world.step(render=show or (capture and annotator is not None))
    if capture and annotator is not None:
        # pause_timeline=False: by default the replicator step pauses physics for good
        rep.orchestrator.step(rt_subframes=2, delta_time=0.0, pause_timeline=False)
        image = annotator.get_data()
        if image.size:  # empty until the renderer has warmed up
            Image.fromarray(image[..., :3]).save(FRAMES / f"frame_{frame:05d}.jpg", quality=90)
            frame += 1
    step += 1

log.writerow([f"{step * PHYSICS_DT:.2f}", "", "", "", "", "", "", "", state if state == "arrived" else "timeout"])
log_file.close()
if ros:
    ros.close()
simulation_app.close()

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
import sys
from pathlib import Path

import numpy as np

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--route", default="data/route_example.geojson",
                    help="relative to the repo root; with --ros only used if /route stays silent")
parser.add_argument("--headless", action="store_true", help="run without the Isaac Sim window")
parser.add_argument("--ros", action="store_true", help="publish poses to ROS 2")
parser.add_argument("--camera", choices=("rover", "astronaut"), default="rover", help="what the view follows")
parser.add_argument("--record", action="store_true", help="save camera frames to media/frames/")
parser.add_argument("--no-lidar", action="store_true", help="leave the lidar out: its beams show in camera images")
parser.add_argument("--walk-speed", type=float, default=0.8,
                    help="astronaut pace in m/s; 0.8 is a suited walk, more makes a quicker demo")
parser.add_argument("--work-scale", type=float, default=2.0,
                    help="simulated seconds per minute of work at a mission target (the demo runs fast)")
parser.add_argument("--capture-fps", type=float, default=10.0, help="frames and ROS messages per simulated second")
parser.add_argument("--max-time", type=float, default=900.0, help="stop after this many simulated seconds")
args = parser.parse_args()

from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": args.headless, "width": 1280, "height": 720})

from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation, SingleRigidPrim
from isaacsim.core.utils.extensions import enable_extension
from isaacsim.core.utils.stage import add_reference_to_stage, open_stage
from isaacsim.core.utils.types import ArticulationAction
from isaacsim.storage.native import get_assets_root_path
from omni.kit.viewport.utility import get_active_viewport
from pxr import Gf, UsdGeom, UsdPhysics

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
TERRAIN = ROOT / "data" / "terrain"
USD_PATH = TERRAIN / "mars_gale.usd"
FRAMES = ROOT / "media" / "frames"
SUIT_USD = ROOT / "sim" / "assets" / "z2_spacesuit" / "z2_spacesuit.usd"
SUIT_FACING_DEG = 90.0  # the suit model faces -y; this turns it to +x, the walking direction
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
MAX_ROVER_SPEED = 1.5  # m/s; faster than this the Jackal leaves the route and tips over on this terrain
UPRIGHT_LIMIT = 0.5  # the rover counts as tipped over when its up axis leans more than 60 degrees
RIGHTING_PAUSE = 3.0  # s after setting it upright before checking again
BALLAST_MASS = 45.0  # kg for the chassis body (the Jackal itself is about 17 kg)
STUCK_SECONDS = 5.0  # driving but moved less than STUCK_METRES in this time: the rover is stuck
STUCK_METRES = 0.3
UNSTICK_AHEAD = 1.5  # m along the route the rover is moved forward when stuck


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
        from sensor_msgs.msg import JointState
        from std_msgs.msg import String

        self._types = PoseStamped, Clock, String
        self._JointState = JointState
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
        self.route_stamp = 0.0
        self.node.create_subscription(Path, "/route", self._on_route, latched)
        # Remote arm control: target angles by joint name, applied until the next command
        self.arm_targets = {}
        self.node.create_subscription(JointState, "/rover/arm/command", self._on_arm_command, 10)
        self.arm_state = self.node.create_publisher(JointState, "/rover/arm/joint_states", 10)
        # Mission: targets and work times from mission_planner, progress back to the dashboard
        self.mission_plan = None
        self.node.create_subscription(String, "/mission/plan", self._on_mission_plan, latched)
        self.mission_progress = self.node.create_publisher(String, "/mission/progress", 10)

    def _on_mission_plan(self, msg):
        self.mission_plan = json.loads(msg.data)

    def publish_progress(self, progress):
        self.mission_progress.publish(self._types[2](data=json.dumps(progress)))

    def _on_arm_command(self, msg):
        self.arm_targets.update(zip(msg.name, msg.position))

    def publish_arm(self, names, positions):
        msg = self._JointState()
        msg.header.stamp = self.node.get_clock().now().to_msg()
        msg.name = list(names)
        msg.position = [float(v) for v in positions]
        self.arm_state.publish(msg)

    def _on_route(self, msg):
        # /route has two latched publishers (planner and mission_planner), and a
        # late-joining one can deliver an old route: only a newer route counts
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        points = [(p.pose.position.x, p.pose.position.y) for p in msg.poses]
        if len(points) > 1 and stamp > self.route_stamp:
            self.route_stamp = stamp
            self.new_route = points

    def poll_route(self):
        """Route points if a new route arrived since the last call, else None."""
        for _ in range(5):  # one callback per spin: route, plan and arm commands may all be waiting
            self._rclpy.spin_once(self.node, timeout_sec=0.0)
        points, self.new_route = self.new_route, None
        return points

    def wait_for_route(self, seconds):
        for _ in range(int(seconds * 10)):
            self._rclpy.spin_once(self.node, timeout_sec=0.1)
            if self.new_route:
                return self.poll_route()
        return None

    def _pose(self, stamp, position, quat_wxyz):
        PoseStamped = self._types[0]
        msg = PoseStamped()
        msg.header.stamp = stamp
        msg.header.frame_id = "map"
        msg.pose.position.x, msg.pose.position.y, msg.pose.position.z = (float(v) for v in position)
        o = msg.pose.orientation
        o.w, o.x, o.y, o.z = (float(v) for v in quat_wxyz)
        return msg

    def publish(self, t, astronaut_position, astronaut_yaw, rover_position, rover_orientation, state):
        _, Clock, String = self._types
        clock = Clock()
        clock.clock.sec = int(t)
        clock.clock.nanosec = int((t - int(t)) * 1e9)
        self.clock.publish(clock)
        heading = (math.cos(astronaut_yaw / 2), 0.0, 0.0, math.sin(astronaut_yaw / 2))
        self.astronaut.publish(self._pose(clock.clock, astronaut_position, heading))
        # Full rover attitude, so the lidar points can be put into the map frame
        self.rover.publish(self._pose(clock.clock, rover_position, rover_orientation))
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
# The Jackal asset carries its own SICK lidar, whose beams are drawn into every
# camera image; the simulation uses its own lidar (sim/sensors.py) instead
built_in_lidar = world.stage.GetPrimAtPath("/World/Rover/base_link/sick_lms1xx_lidar_frame/Lidar")
if built_in_lidar.IsValid():
    built_in_lidar.SetActive(False)
# Ballast low in the chassis: with the arm on top the small rover is top-heavy and
# rolls on 10-20 degree slopes under Mars gravity (real rovers carry batteries low)
ballast = UsdPhysics.MassAPI.Apply(world.stage.GetPrimAtPath("/World/Rover/base_link"))
ballast.CreateMassAttr(BALLAST_MASS)
ballast.CreateCenterOfMassAttr(Gf.Vec3f(0.0, 0.0, -0.04))
if ros:
    from sensors import add_sensors, place_helmet_camera

    add_sensors(world.stage, "/World/Rover", lidar=not args.no_lidar)
from arm import ARM_JOINTS, PRESETS, add_arm
from mission_walk import MissionWalk

add_arm(world.stage, "/World/Rover")

# Astronaut: NASA's Z2 spacesuit if sim/prepare_astronaut.py has made it, else a
# capsule. No physics; placed on the terrain and turned to the walking direction.
astronaut_prim = UsdGeom.Xform.Define(world.stage, "/World/Astronaut")
if SUIT_USD.exists():
    astronaut_prim.GetPrim().GetReferences().AddReference(str(SUIT_USD))
    suit_base = 0.0  # the suit model stands on its own origin
else:
    capsule = UsdGeom.Capsule.Define(world.stage, "/World/Astronaut/Body")
    capsule.CreateRadiusAttr(0.28)
    capsule.CreateHeightAttr(ASTRONAUT_HEIGHT - 0.56)
    capsule.CreateAxisAttr("Z")
    capsule.CreateDisplayColorAttr([Gf.Vec3f(0.92, 0.92, 0.90)])
    suit_base = ASTRONAUT_HEIGHT / 2
astronaut_xform = UsdGeom.Xformable(astronaut_prim)
astronaut_op = astronaut_xform.AddTranslateOp()
astronaut_turn = astronaut_xform.AddRotateZOp()

camera = UsdGeom.Camera.Define(world.stage, "/World/Cameras/Follow")
camera.CreateFocalLengthAttr(18.0)
camera.CreateClippingRangeAttr(Gf.Vec2f(0.05, 20000.0))
camera_op = UsdGeom.Xformable(camera).AddTransformOp()
if not args.headless:
    get_active_viewport().camera_path = "/World/Cameras/Follow"

world.reset()
chassis = SingleRigidPrim("/World/Rover/base_link")
left = [i for i, name in enumerate(rover.dof_names) if "left" in name]
right = [i for i, name in enumerate(rover.dof_names) if "right" in name]
wheels = left + right
arm_index = [rover.dof_names.index(name) for name in ARM_JOINTS]
arm_target = np.array(PRESETS["stow"], dtype=float)
print(f"rover dofs: {rover.dof_names}")

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
log.writerow(["t", "astronaut_x", "astronaut_y", "rover_x", "rover_y", "rover_z", "rover_yaw_deg", "gap_m", "state", "up_z"])

steps_per_frame = max(1, round(1.0 / (args.capture_fps * PHYSICS_DT)))
rover_s, frame, step = 0.0, 0, 0
stuck_since, stuck_from = None, None
righted_at = -RIGHTING_PAUSE
state = "following"
walk = MissionWalk(route, ros.mission_plan if ros else None, args.work_scale, start_s=HEAD_START)
while simulation_app.is_running() and step * PHYSICS_DT < args.max_time:
    t = step * PHYSICS_DT
    points = ros.poll_route() if ros else None
    if points:  # new route from the planner: it starts where the astronaut stands
        route = Route(points)
        walk = MissionWalk(route, ros.mission_plan, args.work_scale)
        rover_s = 0.0
        print(f"t={t:.0f} s: new route, {route.length:.0f} m, {len(walk.stops)} mission stops")
    astronaut_s = walk.step(t, args.walk_speed * PHYSICS_DT if step >= SETTLE_STEPS else 0.0, walk.s - rover_s)
    astronaut_xy = route.point(astronaut_s)
    astronaut_z = ground_height(heights, cell, *astronaut_xy)
    astronaut_yaw = route.heading(astronaut_s)
    astronaut_op.Set(Gf.Vec3d(astronaut_xy[0], astronaut_xy[1], astronaut_z + suit_base))
    astronaut_turn.Set(math.degrees(astronaut_yaw) + SUIT_FACING_DEG)

    position, orientation = rover.get_world_pose()
    # Tilt from the chassis body itself: the asset's root prim does not always follow the physics
    _, (w, x, y, z) = chassis.get_world_pose()
    up_z = 1.0 - 2.0 * (x * x + y * y)
    if up_z < UPRIGHT_LIMIT and step > SETTLE_STEPS and t > righted_at + RIGHTING_PAUSE:
        # Tipped over: put it back on its wheels on the route, as a crew would right a small robot
        righted_at = t
        heading = route.heading(rover_s)
        spot = route.point(rover_s)
        rover.set_world_pose(position=np.array([spot[0], spot[1], ground_height(heights, cell, *spot) + 0.25]),
                             orientation=np.array([math.cos(heading / 2), 0.0, 0.0, math.sin(heading / 2)]))
        rover.set_linear_velocity(np.zeros(3))
        rover.set_angular_velocity(np.zeros(3))
        rover.set_joint_velocities(np.zeros(rover.num_dof))
        print(f"t={t:.0f} s: rover tipped over, set upright on the route", flush=True)
        position, orientation = rover.get_world_pose()
    # Stuck: the small wheels cannot climb some of the 2 m steps in the terrain model
    if state == "following" and step > SETTLE_STEPS:
        if stuck_since is None or np.linalg.norm(position[:2] - stuck_from) > STUCK_METRES:
            stuck_since, stuck_from = t, position[:2].copy()
        elif t - stuck_since > STUCK_SECONDS:
            rover_s = min(rover_s + UNSTICK_AHEAD, max(walk.s - FOLLOW_GAP, 0.0))
            ahead = route.point(rover_s)
            heading = route.heading(rover_s)
            rover.set_world_pose(position=np.array([ahead[0], ahead[1], ground_height(heights, cell, *ahead) + 0.25]),
                                 orientation=np.array([math.cos(heading / 2), 0.0, 0.0, math.sin(heading / 2)]))
            rover.set_linear_velocity(np.zeros(3))
            rover.set_angular_velocity(np.zeros(3))
            print(f"t={t:.0f} s: rover stuck, moved {UNSTICK_AHEAD} m on along the route")
            stuck_since = None
            position, orientation = rover.get_world_pose()
    else:
        stuck_since = None
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
        # Keep up with a sped-up demo walk, within what the small rover can drive
        cruise = min(max(CRUISE_SPEED, 1.15 * args.walk_speed), MAX_ROVER_SPEED)
        speed = min(cruise, 0.8 * room + 0.2) * max(0.0, math.cos(heading_error)) ** 2
        # Gentler turns at speed: a sharp skid turn at 2 m/s rolls the small rover
        skid = float(np.clip(STEER_GAIN * heading_error, -1.0, 1.0)) * min(1.0, CRUISE_SPEED / max(speed, 0.1))
    if step < SETTLE_STEPS:
        speed = skid = 0.0

    velocities = np.zeros(rover.num_dof)
    velocities[left] = (speed - skid) / WHEEL_RADIUS
    velocities[right] = (speed + skid) / WHEEL_RADIUS
    rover.apply_action(ArticulationAction(joint_velocities=velocities[wheels], joint_indices=np.array(wheels)))
    if ros and ros.arm_targets:
        for name, angle in ros.arm_targets.items():
            if name in ARM_JOINTS:
                arm_target[ARM_JOINTS.index(name)] = angle
        ros.arm_targets = {}
    pose = walk.arm_pose(t)  # a mission sample sequence overrides remote control while it runs
    if pose:
        arm_target[:] = PRESETS[pose]
    rover.apply_action(ArticulationAction(joint_positions=arm_target, joint_indices=np.array(arm_index)))

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
            ros.publish(t, (*astronaut_xy, astronaut_z), astronaut_yaw, position, orientation, state)
            place_helmet_camera(world.stage, (*astronaut_xy, astronaut_z + EYE_HEIGHT), astronaut_yaw)
            ros.publish_arm(ARM_JOINTS, rover.get_joint_positions()[arm_index])
            ros.publish_progress(walk.progress(t))
        log.writerow([f"{t:.2f}", f"{astronaut_xy[0]:.2f}", f"{astronaut_xy[1]:.2f}",
                      f"{position[0]:.2f}", f"{position[1]:.2f}", f"{position[2]:.2f}",
                      f"{math.degrees(yaw):.1f}", f"{astronaut_s - rover_s:.1f}", state, f"{up_z:.2f}"])
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

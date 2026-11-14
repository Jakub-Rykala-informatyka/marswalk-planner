"""Drive a rover along a route on the Mars terrain, with physics.

Run with Isaac Sim's python.sh after build_scene.py. The rover is the Clearpath
Jackal from the Isaac Sim asset library, a stand-in for the crew support rover.
Writes a pose log (CSV) and, with --record, camera frames for a video.
"""

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--route", default="data/route_example.geojson", help="relative to the repo root")
parser.add_argument("--headless", action="store_true", help="run without the Isaac Sim window")
parser.add_argument("--record", action="store_true", help="save chase-camera frames to media/frames/")
parser.add_argument("--capture-fps", type=float, default=10.0, help="frames per simulated second")
parser.add_argument("--max-time", type=float, default=600.0, help="stop after this many simulated seconds")
args = parser.parse_args()

from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": args.headless, "width": 1280, "height": 720})

from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.utils.stage import add_reference_to_stage, open_stage
from isaacsim.core.utils.types import ArticulationAction
from isaacsim.storage.native import get_assets_root_path
from pxr import Gf, UsdGeom

ROOT = Path(__file__).resolve().parents[1]
USD_PATH = ROOT / "data" / "terrain" / "mars_gale.usd"
FRAMES = ROOT / "media" / "frames"
LOG_PATH = ROOT / "data" / "preview" / "rover_log.csv"

MARS_GRAVITY = 3.72  # m/s^2
PHYSICS_DT = 1.0 / 60.0
# Jackal geometry, read from the asset
WHEEL_RADIUS = 0.098
CRUISE_SPEED = 1.5  # m/s
LOOKAHEAD = 2.5  # m, pure-pursuit distance
GOAL_TOLERANCE = 1.0  # m
STEER_GAIN = 2.0  # m/s of wheel-speed difference per radian of heading error
SETTLE_STEPS = 30  # let the rover land on the ground before driving


def load_route(path):
    feature = json.loads((ROOT / path).read_text())["features"][0]
    return np.array(feature["geometry"]["coordinates"], dtype=float)


def yaw_of(quat_wxyz):
    w, x, y, z = quat_wxyz
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def pursuit_target(route_xy, position_xy, progress):
    """First route point at least LOOKAHEAD away, searching forward from `progress`."""
    for i in range(progress, len(route_xy)):
        if np.linalg.norm(route_xy[i] - position_xy) >= LOOKAHEAD:
            return i
    return len(route_xy) - 1


def set_camera(camera_op, eye, target):
    view = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1))
    camera_op.Set(view.GetInverse())


route = load_route(args.route)
route_xy = route[:, :2]
start = route[0]
start_yaw = math.atan2(*(route_xy[1] - route_xy[0])[::-1])

open_stage(str(USD_PATH))
world = World(physics_dt=PHYSICS_DT, rendering_dt=PHYSICS_DT, stage_units_in_meters=1.0)
world.get_physics_context().set_gravity(-MARS_GRAVITY)

add_reference_to_stage(get_assets_root_path() + "/Isaac/Robots/Clearpath/Jackal/jackal.usd", "/World/Rover")
rover = SingleArticulation(
    "/World/Rover", name="rover",
    position=np.array([start[0], start[1], start[2] + 0.2]),
    orientation=np.array([math.cos(start_yaw / 2), 0.0, 0.0, math.sin(start_yaw / 2)]),
)
world.scene.add(rover)

camera = UsdGeom.Camera.Define(world.stage, "/World/Cameras/Chase")
camera.CreateFocalLengthAttr(18.0)
camera.CreateClippingRangeAttr(Gf.Vec2f(0.05, 20000.0))
camera_op = UsdGeom.Xformable(camera).AddTransformOp()

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
    product = rep.create.render_product("/World/Cameras/Chase", (1280, 720))
    annotator = rep.AnnotatorRegistry.get_annotator("rgb")
    annotator.attach([product])

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
log_file = LOG_PATH.open("w", newline="")
log = csv.writer(log_file)
log.writerow(["t", "x", "y", "z", "yaw_deg", "goal_dist_m"])

steps_per_frame = max(1, round(1.0 / (args.capture_fps * PHYSICS_DT)))
progress, frame, step = 0, 0, 0
reached = False
while simulation_app.is_running() and step * PHYSICS_DT < args.max_time:
    position, orientation = rover.get_world_pose()
    yaw = yaw_of(orientation)
    goal_dist = float(np.linalg.norm(route_xy[-1] - position[:2]))
    if goal_dist < GOAL_TOLERANCE:
        reached = True
        break

    progress = pursuit_target(route_xy, position[:2], progress)
    to_target = route_xy[progress] - position[:2]
    heading_error = math.atan2(to_target[1], to_target[0]) - yaw
    heading_error = math.atan2(math.sin(heading_error), math.cos(heading_error))
    # Skid steering scrubs sideways, so the turn is a wheel-speed difference
    # proportional to the heading error, not the ideal differential-drive formula
    speed = CRUISE_SPEED * max(0.0, math.cos(heading_error)) ** 2
    skid = float(np.clip(STEER_GAIN * heading_error, -CRUISE_SPEED, CRUISE_SPEED))
    if step < SETTLE_STEPS:
        speed = skid = 0.0

    velocities = np.zeros(rover.num_dof)
    velocities[left] = (speed - skid) / WHEEL_RADIUS
    velocities[right] = (speed + skid) / WHEEL_RADIUS
    rover.apply_action(ArticulationAction(joint_velocities=velocities))

    capture = step % steps_per_frame == 0
    if capture:
        back = np.array([math.cos(yaw), math.sin(yaw), 0.0])
        set_camera(camera_op, position - 3.0 * back + np.array([0.0, 0.0, 1.3]),
                   position + 4.0 * back + np.array([0.0, 0.0, 0.3]))
        log.writerow([f"{step * PHYSICS_DT:.2f}", f"{position[0]:.2f}", f"{position[1]:.2f}",
                      f"{position[2]:.2f}", f"{math.degrees(yaw):.1f}", f"{goal_dist:.1f}"])
        log_file.flush()
    world.step(render=not args.headless or (capture and annotator is not None))
    if capture and annotator is not None:
        # pause_timeline=False: by default the replicator step pauses physics for good
        rep.orchestrator.step(rt_subframes=2, delta_time=0.0, pause_timeline=False)
        image = annotator.get_data()
        if image.size:  # empty until the renderer has warmed up
            Image.fromarray(image[..., :3]).save(FRAMES / f"frame_{frame:05d}.jpg", quality=90)
            frame += 1
    step += 1

log.writerow(["reached" if reached else "timeout", "", "", "", "", ""])
log_file.close()
simulation_app.close()

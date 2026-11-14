"""Unitree Z1 arm mounted on the rover, controlled over ROS 2.

Import after SimulationApp has started. The arm's fixed joint to the world is
re-attached to the rover's base link and its own articulation root is removed,
so the arm becomes part of the rover articulation and moves with it.

  /rover/arm/command       sensor_msgs/JointState, target angles (rad) by joint name
  /rover/arm/joint_states  sensor_msgs/JointState, measured angles, published by the simulation
"""

import json
from pathlib import Path

from isaacsim.core.utils.stage import add_reference_to_stage
from isaacsim.storage.native import get_assets_root_path
from pxr import Gf, Sdf, UsdGeom, UsdPhysics

# Joint names, limits and named poses, shared with the dashboard
_CONFIG = json.loads((Path(__file__).resolve().parents[1] / "data" / "arm_presets.json").read_text())
ARM_JOINTS = [j["name"] for j in _CONFIG["joints"]]
PRESETS = _CONFIG["presets"]
MOUNT = (-0.05, 0.0, 0.30)  # m, arm base on the rover deck, in the rover frame


def add_arm(stage, rover_path):
    """Reference the Z1 under the rover and bolt it to the rover's base link."""
    arm_path = f"{rover_path}/Arm"
    add_reference_to_stage(get_assets_root_path() + "/Isaac/Robots/Unitree/Z1/z1.usd", arm_path)
    base = next(p for p in stage.GetPrimAtPath(rover_path).GetChildren()
                if p.HasAPI(UsdPhysics.RigidBodyAPI) and "base" in p.GetName())

    root_joint = UsdPhysics.FixedJoint(stage.GetPrimAtPath(f"{arm_path}/root_joint"))
    root_joint.GetPrim().RemoveAPI(UsdPhysics.ArticulationRootAPI)
    stage.GetPrimAtPath(f"{arm_path}/root_joint").RemoveAppliedSchema("PhysxArticulationAPI")

    # Joint frame on the base link: where the mount point is, seen from the base link
    cache = UsdGeom.XformCache()
    rover_to_world = cache.GetLocalToWorldTransform(stage.GetPrimAtPath(rover_path))
    base_to_world = cache.GetLocalToWorldTransform(base)
    mount_world = rover_to_world.Transform(Gf.Vec3d(*MOUNT))
    mount_in_base = base_to_world.GetInverse().Transform(mount_world)
    root_joint.CreateBody0Rel().SetTargets([base.GetPath()])
    root_joint.CreateLocalPos0Attr(Gf.Vec3f(*mount_in_base))
    root_joint.CreateLocalRot0Attr(Gf.Quatf(1, 0, 0, 0))
    root_joint.CreateLocalPos1Attr(Gf.Vec3f(0, 0, 0))
    root_joint.CreateLocalRot1Attr(Gf.Quatf(1, 0, 0, 0))

    # Start the arm prim at the mount, so the solver does not have to pull it there
    stage.GetPrimAtPath(arm_path).GetAttribute("xformOp:translate").Set(Gf.Vec3d(*MOUNT))
    return arm_path, str(base.GetPath())

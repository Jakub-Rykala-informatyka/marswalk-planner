"""Rover lidar and the two cameras, published to ROS 2 through an OmniGraph.

Import after SimulationApp has started and the ROS 2 bridge is enabled.

  /rover/points          sensor_msgs/PointCloud2, RTX lidar on the rover, frame rover_lidar
  /rover/camera/image    sensor_msgs/Image, forward camera on the rover
  /astronaut/camera/image sensor_msgs/Image, helmet camera at eye level

The astronaut camera prim is moved by the simulation loop (place_helmet_camera).
"""

import math

import omni.graph.core as og
import omni.kit.commands
from pxr import Gf, UsdGeom

LIDAR_CONFIG, LIDAR_VARIANT = "OS1", "OS1_REV6_32ch10hz512res"  # light model for a laptop GPU
LIDAR_HEIGHT = 0.45  # m above the rover base, see ros/README.md
CAMERA_SIZE = (640, 360)
CAMERA_FRAME_SKIP = 2  # publish every 3rd rendered frame
HELMET_CAMERA = "/World/Cameras/Helmet"


def _camera(stage, path, focal_length):
    camera = UsdGeom.Camera.Define(stage, path)
    camera.CreateFocalLengthAttr(focal_length)
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.05, 20000.0))
    return camera


def place_helmet_camera(stage, eye, yaw):
    """Point the helmet camera along the walking direction, a little down."""
    forward = Gf.Vec3d(math.cos(yaw), math.sin(yaw), -0.12)
    # Just in front of the helmet bubble (it reaches 0.38 m forward), so the
    # camera is not inside the suit model
    visor = Gf.Vec3d(*eye) + 0.5 * Gf.Vec3d(forward[0], forward[1], 0.0)
    view = Gf.Matrix4d().SetLookAt(visor, visor + forward, Gf.Vec3d(0, 0, 1))
    xform = UsdGeom.Xformable(stage.GetPrimAtPath(HELMET_CAMERA))
    ops = xform.GetOrderedXformOps()
    (ops[0] if ops else xform.AddTransformOp()).Set(view.GetInverse())


def add_sensors(stage, rover_path):
    """Create the sensors under the rover and the graph that publishes them."""
    base = f"{rover_path}/base_link" if stage.GetPrimAtPath(f"{rover_path}/base_link") else rover_path

    _, lidar = omni.kit.commands.execute(
        "IsaacSensorCreateRtxLidar", path="Lidar", parent=base, config=LIDAR_CONFIG, variant=LIDAR_VARIANT,
        translation=Gf.Vec3d(0.0, 0.0, LIDAR_HEIGHT), orientation=Gf.Quatd(1, 0, 0, 0))

    # Rover camera: forward, at the front of the deck. USD cameras look along -Z,
    # so turn it to look along the rover's +X with +Z up
    rover_camera = _camera(stage, f"{base}/FrontCamera", 14.0)
    xform = UsdGeom.Xformable(rover_camera)
    xform.AddTranslateOp().Set(Gf.Vec3d(0.25, 0.0, 0.35))
    xform.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, -90.0))
    _camera(stage, HELMET_CAMERA, 18.0)

    keys = og.Controller.Keys
    width, height = CAMERA_SIZE
    og.Controller.edit(
        {"graph_path": "/ROS2Sensors", "evaluator_name": "execution"},
        {
            keys.CREATE_NODES: [
                ("tick", "omni.graph.action.OnPlaybackTick"),
                ("run_once", "isaacsim.core.nodes.OgnIsaacRunOneSimulationFrame"),
                ("lidar_product", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
                ("lidar", "isaacsim.ros2.bridge.ROS2RtxLidarHelper"),
                ("rover_product", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
                ("rover_camera", "isaacsim.ros2.bridge.ROS2CameraHelper"),
                ("helmet_product", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
                ("helmet_camera", "isaacsim.ros2.bridge.ROS2CameraHelper"),
            ],
            keys.CONNECT: [
                ("tick.outputs:tick", "run_once.inputs:execIn"),
                ("run_once.outputs:step", "lidar_product.inputs:execIn"),
                ("run_once.outputs:step", "rover_product.inputs:execIn"),
                ("run_once.outputs:step", "helmet_product.inputs:execIn"),
                ("lidar_product.outputs:execOut", "lidar.inputs:execIn"),
                ("lidar_product.outputs:renderProductPath", "lidar.inputs:renderProductPath"),
                ("rover_product.outputs:execOut", "rover_camera.inputs:execIn"),
                ("rover_product.outputs:renderProductPath", "rover_camera.inputs:renderProductPath"),
                ("helmet_product.outputs:execOut", "helmet_camera.inputs:execIn"),
                ("helmet_product.outputs:renderProductPath", "helmet_camera.inputs:renderProductPath"),
            ],
            keys.SET_VALUES: [
                ("lidar_product.inputs:cameraPrim", [str(lidar.GetPath())]),
                ("lidar.inputs:type", "point_cloud"),
                ("lidar.inputs:fullScan", True),
                ("lidar.inputs:topicName", "/rover/points"),
                ("lidar.inputs:frameId", "rover_lidar"),
                ("rover_product.inputs:cameraPrim", [str(rover_camera.GetPath())]),
                ("rover_product.inputs:width", width),
                ("rover_product.inputs:height", height),
                ("rover_camera.inputs:type", "rgb"),
                ("rover_camera.inputs:topicName", "/rover/camera/image"),
                ("rover_camera.inputs:frameId", "rover_camera"),
                ("rover_camera.inputs:frameSkipCount", CAMERA_FRAME_SKIP),
                ("helmet_product.inputs:cameraPrim", [HELMET_CAMERA]),
                ("helmet_product.inputs:width", width),
                ("helmet_product.inputs:height", height),
                ("helmet_camera.inputs:type", "rgb"),
                ("helmet_camera.inputs:topicName", "/astronaut/camera/image"),
                ("helmet_camera.inputs:frameId", "helmet_camera"),
                ("helmet_camera.inputs:frameSkipCount", CAMERA_FRAME_SKIP),
            ],
        },
    )
    return base

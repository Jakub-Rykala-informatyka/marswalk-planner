"""Rover lidar and the two cameras, published to ROS 2 through an OmniGraph.

Import after SimulationApp has started and the ROS 2 bridge is enabled.

  /rover/points          sensor_msgs/PointCloud2, RTX lidar on the rover, frame rover_lidar
  /rover/camera/image    sensor_msgs/Image, forward camera on the rover
  /astronaut/camera/image sensor_msgs/Image, helmet camera at eye level
  /rover/arm_camera/image sensor_msgs/Image, operator view of the arm from behind the rover

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


def add_sensors(stage, rover_path, lidar=True):
    """Create the sensors under the rover and the graph that publishes them.

    The RTX lidar's beams show up as coloured lines in every camera image;
    lidar=False leaves it out, for recording video.
    """
    base = f"{rover_path}/base_link" if stage.GetPrimAtPath(f"{rover_path}/base_link") else rover_path

    lidar_prim = None
    if lidar:
        _, lidar_prim = omni.kit.commands.execute(
            "IsaacSensorCreateRtxLidar", path="Lidar", parent=base, config=LIDAR_CONFIG, variant=LIDAR_VARIANT,
            translation=Gf.Vec3d(0.0, 0.0, LIDAR_HEIGHT), orientation=Gf.Quatd(1, 0, 0, 0))

    # Rover camera: forward, at the front of the deck. USD cameras look along -Z,
    # so turn it to look along the rover's +X with +Z up
    rover_camera = _camera(stage, f"{base}/FrontCamera", 14.0)
    xform = UsdGeom.Xformable(rover_camera)
    xform.AddTranslateOp().Set(Gf.Vec3d(0.25, 0.0, 0.35))
    xform.AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, -90.0))
    _camera(stage, HELMET_CAMERA, 18.0)

    # Operator view: behind and above the rover, looking at the arm and the ground in front
    arm_camera = _camera(stage, f"{base}/ArmCamera", 12.0)
    view = Gf.Matrix4d().SetLookAt(Gf.Vec3d(-1.3, 0.9, 1.1), Gf.Vec3d(0.4, 0.0, 0.25), Gf.Vec3d(0, 0, 1))
    UsdGeom.Xformable(arm_camera).AddTransformOp().Set(view.GetInverse())

    keys = og.Controller.Keys
    width, height = CAMERA_SIZE
    graph = (
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
                ("arm_product", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
                ("arm_camera", "isaacsim.ros2.bridge.ROS2CameraHelper"),
            ],
            keys.CONNECT: [
                ("tick.outputs:tick", "run_once.inputs:execIn"),
                ("run_once.outputs:step", "lidar_product.inputs:execIn"),
                ("run_once.outputs:step", "rover_product.inputs:execIn"),
                ("run_once.outputs:step", "helmet_product.inputs:execIn"),
                ("run_once.outputs:step", "arm_product.inputs:execIn"),
                ("arm_product.outputs:execOut", "arm_camera.inputs:execIn"),
                ("arm_product.outputs:renderProductPath", "arm_camera.inputs:renderProductPath"),
                ("lidar_product.outputs:execOut", "lidar.inputs:execIn"),
                ("lidar_product.outputs:renderProductPath", "lidar.inputs:renderProductPath"),
                ("rover_product.outputs:execOut", "rover_camera.inputs:execIn"),
                ("rover_product.outputs:renderProductPath", "rover_camera.inputs:renderProductPath"),
                ("helmet_product.outputs:execOut", "helmet_camera.inputs:execIn"),
                ("helmet_product.outputs:renderProductPath", "helmet_camera.inputs:renderProductPath"),
            ],
            keys.SET_VALUES: [
                ("lidar_product.inputs:cameraPrim", [str(lidar_prim.GetPath()) if lidar_prim else ""]),
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
                ("arm_product.inputs:cameraPrim", [str(arm_camera.GetPath())]),
                ("arm_product.inputs:width", width),
                ("arm_product.inputs:height", height),
                ("arm_camera.inputs:type", "rgb"),
                ("arm_camera.inputs:topicName", "/rover/arm_camera/image"),
                ("arm_camera.inputs:frameId", "arm_camera"),
                ("arm_camera.inputs:frameSkipCount", CAMERA_FRAME_SKIP),
            ],
        },
    )
    if not lidar:
        graph[1][keys.CREATE_NODES] = [n for n in graph[1][keys.CREATE_NODES] if not n[0].startswith("lidar")]
        graph[1][keys.CONNECT] = [c for c in graph[1][keys.CONNECT] if "lidar" not in c[0] + c[1]]
        graph[1][keys.SET_VALUES] = [v for v in graph[1][keys.SET_VALUES] if not v[0].startswith("lidar")]
    og.Controller.edit(*graph)
    return base

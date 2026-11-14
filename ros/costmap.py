"""ROS 2 node that builds cost maps for walking and for the crew rover from the NASA layers.

Subscribes to /nasa/slope, /nasa/roughness and /nasa/dose_rate (from
nasa_layers) and publishes /costmap/walk and /costmap/rover as latched
OccupancyGrids: 0 = free, 1..99 = harder going, 100 = keep out. Weights and
limits are ROS parameters; changing one recomputes the maps, for example:

  ros2 param set /costmap walk.max_slope_deg 20.0
"""

import array

import numpy as np
import rclpy
from nav_msgs.msg import OccupancyGrid
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                     reliability=ReliabilityPolicy.RELIABLE)

# Value of 100 in each /nasa/* grid, as published by nasa_layers (see ros/README.md)
SLOPE_FULL_DEG = 45.0
ROUGHNESS_FULL_M = 1.0

# variant: {parameter: default}. Assumptions to tune, not measured limits.
DEFAULTS = {
    # Walking in a suit: easy up to about 15 deg, forbidden from 25 deg
    "walk": {"max_slope_deg": 25.0, "comfort_slope_deg": 15.0, "slope_weight": 70.0,
             "max_roughness_m": 2.0, "roughness_weight": 15.0, "dose_weight": 10.0},
    # Pressurised rover: gentler slopes, no boulder fields, cabin shields the crew
    "rover": {"max_slope_deg": 15.0, "comfort_slope_deg": 8.0, "slope_weight": 70.0,
              "max_roughness_m": 1.0, "roughness_weight": 25.0, "dose_weight": 0.0},
}
LAYERS = ("slope", "roughness", "dose_rate")


def grid_values(msg):
    data = np.frombuffer(bytes(np.array(msg.data, dtype=np.int8)), dtype=np.int8)
    return data.reshape(msg.info.height, msg.info.width).astype(np.float32)


def cost(slope_deg, roughness_m, dose_share, p):
    """Cost 0..100 per cell; dose_share is the dose rate as a share of open ground."""
    over = np.clip((slope_deg - p["comfort_slope_deg"]) / (p["max_slope_deg"] - p["comfort_slope_deg"]), 0, 1)
    gentle = np.clip(slope_deg / p["comfort_slope_deg"], 0, 1)
    value = (p["slope_weight"] * (0.2 * gentle + 0.8 * over ** 2)
             + p["roughness_weight"] * np.clip(roughness_m / p["max_roughness_m"], 0, 1)
             + p["dose_weight"] * dose_share)
    value = np.clip(np.rint(value), 0, 99)
    value[(slope_deg >= p["max_slope_deg"]) | (roughness_m >= p["max_roughness_m"])] = 100
    return value.astype(np.int8)


class Costmap(Node):
    def __init__(self):
        super().__init__("costmap")
        for variant, params in DEFAULTS.items():
            for name, value in params.items():
                self.declare_parameter(f"{variant}.{name}", value)
        self.layers = {}
        self.info = None
        self.publishers_ = {v: self.create_publisher(OccupancyGrid, f"/costmap/{v}", LATCHED) for v in DEFAULTS}
        for name in LAYERS:
            self.create_subscription(OccupancyGrid, f"/nasa/{name}",
                                     lambda msg, name=name: self.on_layer(name, msg), LATCHED)
        self.add_on_set_parameters_callback(self.on_parameters)
        self.pending = False
        self.create_timer(0.2, self.publish_if_pending)

    def on_layer(self, name, msg):
        self.layers[name] = grid_values(msg)
        self.info = msg.info
        self.pending = True

    def on_parameters(self, _params):
        self.pending = True  # recompute after the new values are stored
        return SetParametersResult(successful=True)

    def params(self, variant):
        return {name: self.get_parameter(f"{variant}.{name}").value for name in DEFAULTS[variant]}

    def publish_if_pending(self):
        if not self.pending or len(self.layers) < len(LAYERS):
            return
        self.pending = False
        slope = self.layers["slope"] / 100.0 * SLOPE_FULL_DEG
        roughness = self.layers["roughness"] / 100.0 * ROUGHNESS_FULL_M
        dose_share = self.layers["dose_rate"] / 100.0
        for variant, publisher in self.publishers_.items():
            values = cost(slope, roughness, dose_share, self.params(variant))
            msg = OccupancyGrid()
            msg.header.frame_id = "map"
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.info = self.info
            msg.data = array.array("b", values.tobytes())
            publisher.publish(msg)
            self.get_logger().info(f"/costmap/{variant}: keep out {np.mean(values == 100):.0%} of the patch")


def main():
    rclpy.init()
    rclpy.spin(Costmap())


if __name__ == "__main__":
    main()

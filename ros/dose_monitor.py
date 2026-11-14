"""ROS 2 node that tracks the astronaut's radiation dose during the walk.

Subscribes to the dose-rate grid from nasa_layers and to the astronaut pose,
reads the rate under the astronaut and integrates it over simulation time.
Publishes /astronaut/dose_rate (uSv/h) and /astronaut/dose (uSv this walk).
"""

import json
from pathlib import Path

import numpy as np
import rclpy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Float32

ROOT = Path(__file__).resolve().parents[1]
LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                     reliability=ReliabilityPolicy.RELIABLE)


class DoseMonitor(Node):
    def __init__(self):
        super().__init__("dose_monitor")
        meta = json.loads((ROOT / "data" / "meta.json").read_text())
        self.full_rate = meta["dose_model"]["open_ground_uSv_per_h"]  # grid value 100
        self.grid = None
        self.dose = 0.0
        self.last_t = None
        self.create_subscription(OccupancyGrid, "/nasa/dose_rate", self.on_grid, LATCHED)
        self.create_subscription(PoseStamped, "/astronaut/pose", self.on_pose, 10)
        self.rate_pub = self.create_publisher(Float32, "/astronaut/dose_rate", 10)
        self.dose_pub = self.create_publisher(Float32, "/astronaut/dose", 10)

    def on_grid(self, msg):
        info = msg.info
        values = np.frombuffer(bytes(np.array(msg.data, dtype=np.int8)), dtype=np.int8)
        self.grid = (values.reshape(info.height, info.width).astype(np.float32) / 100.0 * self.full_rate,
                     info.resolution, info.origin.position.x, info.origin.position.y)
        self.get_logger().info(f"dose grid {info.width} x {info.height}, {info.resolution:.2f} m")

    def on_pose(self, msg):
        if self.grid is None:
            return
        rates, cell, x0, y0 = self.grid
        ix = int((msg.pose.position.x - x0) / cell)
        iy = int((msg.pose.position.y - y0) / cell)
        if not (0 <= iy < rates.shape[0] and 0 <= ix < rates.shape[1]):
            return
        rate = float(rates[iy, ix])

        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if self.last_t is not None and t < self.last_t:
            self.dose = 0.0  # simulation restarted, a new walk begins
        elif self.last_t is not None:
            self.dose += rate * (t - self.last_t) / 3600.0
        self.last_t = t

        self.rate_pub.publish(Float32(data=rate))
        self.dose_pub.publish(Float32(data=self.dose))


def main():
    rclpy.init()
    rclpy.spin(DoseMonitor())


if __name__ == "__main__":
    main()

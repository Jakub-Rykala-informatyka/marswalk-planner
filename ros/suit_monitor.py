"""ROS 2 node that simulates the suit consumables and checks the safe return.

Subscribes to /astronaut/pose and /nasa/slope. Oxygen and battery drain over
simulation time, faster when walking and on slopes. The return point is where
the walk began, where the crew rover is parked. The way back is taken as the
distance walked so far (the same way back), at walking pace plus a reserve.

Publishes /suit/status (std_msgs/String with JSON, for the dashboard and the
HUD) and /suit/return_point (geometry_msgs/PoseStamped, latched).
All rates and reserves are assumptions, set as ROS parameters.
"""

import json
import math

import numpy as np
import rclpy
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                     reliability=ReliabilityPolicy.RELIABLE)
SLOPE_FULL_DEG = 45.0  # value 100 in /nasa/slope


class SuitMonitor(Node):
    def __init__(self):
        super().__init__("suit_monitor")
        self.declare_parameter("o2_hours", 8.0)  # endurance at a steady walk on flat ground
        self.declare_parameter("battery_hours", 8.0)
        self.declare_parameter("rest_factor", 0.6)  # consumption standing still, share of walking
        self.declare_parameter("slope_factor", 0.04)  # extra consumption per degree of slope
        self.declare_parameter("walk_speed", 0.8)  # m/s on the way back
        self.declare_parameter("reserve_min", 30.0)  # oxygen that must be left on arrival
        self.slope = None
        self.reset()
        self.create_subscription(OccupancyGrid, "/nasa/slope", self.on_slope, LATCHED)
        self.create_subscription(PoseStamped, "/astronaut/pose", self.on_pose, 10)
        self.create_subscription(String, "/rover/config", self.on_rover_config, LATCHED)
        self.spare_o2_hours = 0.0
        self.spare_in_field = False
        self.support_rover = None
        self.status_pub = self.create_publisher(String, "/suit/status", 10)
        self.return_pub = self.create_publisher(PoseStamped, "/suit/return_point", LATCHED)

    def on_rover_config(self, msg):
        config = json.loads(msg.data)
        self.support_rover = config.get("rover_name")
        self.spare_o2_hours = float(config.get("extra_o2_hours", 0))
        # The helper robot walks with the astronaut, so its spare oxygen can be
        # used in the field; a crew rover waits at the return point.
        self.spare_in_field = config.get("rover") == "helper_robot"

    def reset(self):
        self.o2 = 1.0  # share of a full tank
        self.battery = 1.0
        self.walked = 0.0
        self.last = None  # (t, x, y)
        self.return_point = None

    def on_slope(self, msg):
        info = msg.info
        values = np.frombuffer(bytes(np.array(msg.data, dtype=np.int8)), dtype=np.int8)
        self.slope = (values.reshape(info.height, info.width).astype(np.float32) / 100.0 * SLOPE_FULL_DEG,
                      info.resolution, info.origin.position.x, info.origin.position.y)

    def slope_at(self, x, y):
        if self.slope is None:
            return 0.0
        grid, res, x0, y0 = self.slope
        iy = min(max(int((y - y0) / res), 0), grid.shape[0] - 1)
        ix = min(max(int((x - x0) / res), 0), grid.shape[1] - 1)
        return float(grid[iy, ix])

    def on_pose(self, msg):
        p = self.get_parameter
        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        x, y = msg.pose.position.x, msg.pose.position.y
        if self.last is not None and t < self.last[0]:
            self.reset()  # simulation restarted, a new walk begins
        if self.return_point is None:
            self.return_point = (x, y)
            ret = PoseStamped()
            ret.header = msg.header
            ret.pose.position.x, ret.pose.position.y = x, y
            ret.pose.orientation.w = 1.0
            self.return_pub.publish(ret)

        slope = self.slope_at(x, y)
        if self.last is not None:
            dt = t - self.last[0]
            step = math.hypot(x - self.last[1], y - self.last[2])
            self.walked += step
            moving = step / dt > 0.1 if dt > 0 else False
            load = (1.0 if moving else p("rest_factor").value) * (1.0 + p("slope_factor").value * slope)
            self.o2 = max(0.0, self.o2 - load * dt / (p("o2_hours").value * 3600.0))
            self.battery = max(0.0, self.battery - dt / (p("battery_hours").value * 3600.0))
        self.last = (t, x, y)

        o2_left_min = self.o2 * p("o2_hours").value * 60.0
        return_min = self.walked / p("walk_speed").value / 60.0
        field_spare_min = self.spare_o2_hours * 60.0 if self.spare_in_field else 0.0
        margin_min = o2_left_min + field_spare_min - return_min - p("reserve_min").value
        status = {
            "o2_pct": round(self.o2 * 100, 1),
            "o2_left_min": round(o2_left_min, 1),
            "battery_pct": round(self.battery * 100, 1),
            "walked_m": round(self.walked, 1),
            "return_point": [round(v, 1) for v in self.return_point],
            "return_m": round(self.walked, 1),
            "return_min": round(return_min, 1),
            "margin_min": round(margin_min, 1),
            # turn back while a quarter of the reserve is still spare
            "turn_back": margin_min < 0.25 * p("reserve_min").value,
            "slope_deg": round(slope, 1),
            "support_rover": self.support_rover,
            "spare_o2_h": self.spare_o2_hours,
            "spare_in_field": self.spare_in_field,
        }
        self.status_pub.publish(String(data=json.dumps(status)))


def main():
    rclpy.init()
    rclpy.spin(SuitMonitor())


if __name__ == "__main__":
    main()

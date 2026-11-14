"""ROS 2 node that publishes the NASA-derived terrain layers as occupancy grids.

Each layer in data/layers/*.npy goes out once on /nasa/<name> with transient
local durability, so nodes started later (cost map, dose monitor, RViz) still
receive it. Grid values are 0..100; the scale of each layer is in
data/meta.json and ros/README.md.
"""

import array
import json
from pathlib import Path

import numpy as np
import rclpy
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

ROOT = Path(__file__).resolve().parents[1]
LAYERS = ROOT / "data" / "layers"

# name: layer value mapped to 100 (0 maps to 0)
SCALES = {
    "slope": 45.0,  # deg, steeper is clipped to 100
    "roughness": 1.0,  # m
    "sky_view": 1.0,  # fraction of open sky
    "dose_rate": None,  # filled from data/meta.json: open-ground rate from RAD
}

LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                     reliability=ReliabilityPolicy.RELIABLE)


def to_grid(values, scale, cell, stamp):
    msg = OccupancyGrid()
    msg.header.frame_id = "map"
    msg.header.stamp = stamp
    msg.info.map_load_time = stamp
    msg.info.resolution = float(cell)
    msg.info.height, msg.info.width = values.shape
    # .npy samples sit on cell centres at i * cell, grid cells start at the origin
    msg.info.origin.position.x = -cell / 2
    msg.info.origin.position.y = -cell / 2
    msg.info.origin.orientation.w = 1.0
    scaled = np.clip(np.rint(values / scale * 100.0), 0, 100).astype(np.int8)
    msg.data = array.array("b", scaled.tobytes())  # row 0 is the south edge, as in the .npy
    return msg


class NasaLayers(Node):
    def __init__(self):
        super().__init__("nasa_layers")
        meta = json.loads((ROOT / "data" / "meta.json").read_text())
        SCALES["dose_rate"] = meta["dose_model"]["open_ground_uSv_per_h"]
        stamp = self.get_clock().now().to_msg()
        self.publishers_ = []
        for name, scale in SCALES.items():
            publisher = self.create_publisher(OccupancyGrid, f"/nasa/{name}", LATCHED)
            publisher.publish(to_grid(np.load(LAYERS / f"{name}.npy"), scale, meta["cell_m"], stamp))
            self.publishers_.append(publisher)
            self.get_logger().info(f"/nasa/{name}: 100 = {scale:g} {meta['layers'][name]['unit']}")


def main():
    rclpy.init()
    rclpy.spin(NasaLayers())


if __name__ == "__main__":
    main()

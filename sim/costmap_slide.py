"""Presentation slide: how the NASA layers combine into the cost map and the walking route.

Runs the same cost model and A* search as the ROS nodes (ros/cost_model.py) on
the layers in data/layers, with the walking defaults, and draws the steps as
tilted map tiles joined by arrows:

  1 NASA data (dose, roughness, slope) -> 2 cost of each factor -> 3 cost map -> 4 A* route

Writes media/slides/costmap_pipeline.png (1920 x 1080). Plain Python: numpy and Pillow.
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ros"))
from cost_model import DEFAULTS, astar, coarsen, cost, nearest_free  # noqa: E402

LAYERS = ROOT / "data" / "layers"
OUT = ROOT / "media" / "slides" / "costmap_pipeline.png"
W, H = 1920, 1080
TEX = 512  # texture size of each tile before it is tilted

# Same scales and planner defaults as ros/nasa_layers.py and ros/planner.py
SLOPE_FULL_DEG, ROUGHNESS_FULL_M = 45.0, 2.0
COARSE, COST_SCALE, WALK_SPEED = 2, 25.0, 0.8

BG = (14, 17, 26)
INK = (236, 238, 242)
MUTED = (150, 158, 175)
ACCENT = (0, 214, 240)
KEEP_OUT = (226, 52, 52)
RAMP = [(242, 234, 216), (222, 150, 74), (150, 52, 40), (52, 16, 30)]  # cheap to expensive

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


def ramp(share):
    """0..1 to the cheap-to-expensive colour ramp, as an RGB array."""
    share = np.clip(share, 0, 1) * (len(RAMP) - 1)
    low = np.minimum(np.floor(share).astype(int), len(RAMP) - 2)
    t = (share - low)[..., None]
    stops = np.array(RAMP, float)
    return (stops[low] * (1 - t) + stops[low + 1] * t).astype(np.uint8)


def grid_to_image(rgb):
    """.npy rows start at the south edge; images start at the north edge."""
    return Image.fromarray(np.flipud(rgb)).convert("RGBA")


def grey(values, low, high):
    g = (np.clip((values - low) / (high - low), 0, 1) * 255).astype(np.uint8)
    return np.dstack([g, g, g])


def homography(src, dst):
    rows, rhs = [], []
    for (x, y), (u, v) in zip(src, dst):
        rows += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        rhs += [u, v]
    h = np.linalg.solve(np.array(rows, float), np.array(rhs, float))
    return np.append(h, 1.0).reshape(3, 3)


class Tile:
    """A map tilted into a parallelogram: top edge shifted right by the skew."""

    def __init__(self, x, y, width, depth, skew):
        self.x, self.y, self.width, self.depth, self.skew = x, y, width, depth, skew

    @property
    def corners(self):  # NW, NE, SE, SW on the slide
        x, y, w, d, s = self.x, self.y, self.width, self.depth, self.skew
        return np.array([[x + s, y], [x + s + w, y], [x + w, y + d], [x, y + d]], float)

    @property
    def left(self):
        return (self.x + self.skew / 2, self.y + self.depth / 2)

    @property
    def right(self):
        return (self.x + self.width + self.skew / 2, self.y + self.depth / 2)

    @property
    def top(self):
        return (self.x + self.skew + self.width / 2, self.y)

    @property
    def bottom(self):
        return (self.x + self.width / 2, self.y + self.depth)

    def paste(self, slide, image):
        image = image.resize((TEX, TEX), Image.BICUBIC)
        src = np.array([[0, 0], [TEX, 0], [TEX, TEX], [0, TEX]], float)
        back = np.linalg.inv(homography(src, self.corners))
        warped = image.transform((W, H), Image.PERSPECTIVE, tuple((back / back[2, 2]).flatten()[:8]), Image.BICUBIC)
        # A soft drop shadow, then the tile and a thin outline
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).polygon([tuple(p + [10, 14]) for p in self.corners], fill=(0, 0, 0, 110))
        slide.alpha_composite(shadow)
        slide.alpha_composite(warped)
        ImageDraw.Draw(slide).polygon([tuple(p) for p in self.corners], outline=(255, 255, 255, 70), width=1)


def arrow(draw, start, end, colour=INK, width=4, head=16):
    (x0, y0), (x1, y1) = start, end
    angle = math.atan2(y1 - y0, x1 - x0)
    tip_base = (x1 - head * math.cos(angle), y1 - head * math.sin(angle))
    draw.line([start, tip_base], fill=colour, width=width)
    left = (x1 - head * math.cos(angle - 0.45), y1 - head * math.sin(angle - 0.45))
    right = (x1 - head * math.cos(angle + 0.45), y1 - head * math.sin(angle + 0.45))
    draw.polygon([end, left, right], fill=colour)


def label(draw, xy, title, detail=None, anchor="la"):
    draw.text(xy, title, font=font(22, bold=True), fill=INK, anchor=anchor)
    if detail:
        x, y = xy
        for i, line in enumerate(detail.split("\n")):
            draw.text((x, y + 30 + i * 24), line, font=font(18), fill=MUTED, anchor=anchor)


def step_header(draw, x, y, number, text):
    draw.ellipse([x, y, x + 34, y + 34], fill=ACCENT)
    draw.text((x + 17, y + 17), str(number), font=font(20, bold=True), fill=BG, anchor="mm")
    draw.text((x + 46, y + 17), text, font=font(24, bold=True), fill=INK, anchor="lm")


def compute():
    meta = json.loads((ROOT / "data" / "meta.json").read_text())
    open_rate = meta["dose_model"]["open_ground_uSv_per_h"]
    cell = meta["cell_m"]
    raw = {name: np.load(LAYERS / f"{name}.npy") for name in ("slope", "roughness", "dose_rate")}

    # What the cost map node receives: each layer as a 0..100 occupancy grid
    quantise = lambda v, full: np.clip(np.rint(v / full * 100), 0, 100) / 100
    slope = quantise(raw["slope"], SLOPE_FULL_DEG) * SLOPE_FULL_DEG
    roughness = quantise(raw["roughness"], ROUGHNESS_FULL_M) * ROUGHNESS_FULL_M
    dose_share = quantise(raw["dose_rate"], open_rate)

    p = DEFAULTS["walk"]
    over = np.clip((slope - p["comfort_slope_deg"]) / (p["max_slope_deg"] - p["comfort_slope_deg"]), 0, 1)
    gentle = np.clip(slope / p["comfort_slope_deg"], 0, 1)
    terms = {
        "slope": p["slope_weight"] * (0.2 * gentle + 0.8 * over ** 2),
        "roughness": p["roughness_weight"] * np.clip(roughness / p["max_roughness_m"], 0, 1),
        "dose": p["dose_weight"] * dose_share,
    }
    total = cost(slope, roughness, dose_share, p).astype(np.int16)

    # The route the planner node would publish: parking -> boxwork field west (mission target B)
    mission = json.loads((ROOT / "data" / "mission_boxwork.json").read_text())
    start_xy = (mission["start"]["x"], mission["start"]["y"])
    target = next(t for t in mission["targets"] if t["id"] == "B")
    goal_xy = (target["x"], target["y"])
    coarse = coarsen(total, COARSE, np.max)
    origin = -cell / 2
    to_cell = lambda xy: (int((xy[1] - origin) / (cell * COARSE)), int((xy[0] - origin) / (cell * COARSE)))
    start, goal = nearest_free(coarse, to_cell(start_xy)), nearest_free(coarse, to_cell(goal_xy))
    cells = astar(coarse, start, goal, COST_SCALE)
    points = [(origin + (c[1] + 0.5) * cell * COARSE, origin + (c[0] + 0.5) * cell * COARSE) for c in cells]
    steps = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])]
    dose = sum(float(raw["dose_rate"][min(int(y / cell), total.shape[0] - 1), min(int(x / cell), total.shape[1] - 1)])
               * s / WALK_SPEED / 3600 for (x, y), s in zip(points[1:], steps))
    straight = math.hypot(goal_xy[0] - start_xy[0], goal_xy[1] - start_xy[1])
    stats = {
        "keep_out": float(np.mean(total == 100)),
        "length": sum(steps),
        "straight": straight,
        "minutes": sum(steps) / WALK_SPEED / 60,
        "dose": dose,
        "max_cost": int(max(coarse[c] for c in cells)),
        "target": target["name"],
    }
    return raw, terms, total, points, cell, stats, p


def main():
    raw, terms, total, points, cell, stats, p = compute()
    n = total.shape[0]

    slide = Image.new("RGBA", (W, H), BG + (255,))
    draw = ImageDraw.Draw(slide)
    draw.text((70, 52), "From NASA data to a safe walking route", font=font(46, bold=True), fill=INK)
    draw.text((72, 114), "Gale crater, lower Mount Sharp: 2 x 2 km HiRISE patch, 2 m cells. "
                         "The same code runs live in our ROS 2 cost map and planner nodes.",
              font=font(21), fill=MUTED)

    tw, td, sk = 330, 128, 70  # tile width, depth and skew
    rows = [250, 470, 690]
    col1, col2 = 70, 600

    # 1. NASA data, top to bottom: radiation, surface, terrain (as in the sketch)
    step_header(draw, col1, 186, 1, "NASA data")
    inputs = [
        (grid_to_image(grey(raw["dose_rate"], 14.0, 26.7)), "Radiation dose rate",
         "MSL RAD 0.64 mSv/day x open sky\n14–27 µSv/h (model)"),
        (grid_to_image(grey(raw["roughness"], 0.0, 2.0)), "Surface roughness",
         "HiRISE DTM, 1 m posts\n0–2 m bumps per cell"),
        (grid_to_image(grey(raw["slope"], 0.0, 45.0)), "Terrain slope",
         "HiRISE DTM, 1 m posts\n0–45° (white = steep)"),
    ]
    factors = [
        (terms["dose"] / p["dose_weight"], None, "Dose cost  × 10",
         "more open sky = more dose"),
        (terms["roughness"] / p["roughness_weight"], raw["roughness"] >= p["max_roughness_m"], "Roughness cost  × 15",
         f"keep out from {p['max_roughness_m']:g} m"),
        (terms["slope"] / p["slope_weight"], raw["slope"] >= p["max_slope_deg"], "Slope cost  × 70",
         f"easy below {p['comfort_slope_deg']:g}°, keep out from {p['max_slope_deg']:g}°"),
    ]
    step_header(draw, col2, 186, 2, "Cost of each factor")

    tiles2 = []
    for row, (image, title, detail), (share, banned, ftitle, fdetail) in zip(rows, inputs, factors):
        t1 = Tile(col1, row, tw, td, sk)
        t1.paste(slide, image)
        label(draw, (col1, row + td + 10), title, detail)

        rgb = ramp(share)
        if banned is not None:
            rgb[banned] = KEEP_OUT
        t2 = Tile(col2, row, tw, td, sk)
        t2.paste(slide, grid_to_image(rgb))
        label(draw, (col2, row + td + 10), ftitle, fdetail)
        tiles2.append(t2)
        arrow(draw, (t1.right[0] + 30, t1.right[1]), (t2.left[0] - 20, t2.left[1]))

    # 3. Cost map: the weighted sum, with keep-out cells in red
    col3, row3, bw, bd, bsk = 1070, 240, 400, 170, 90
    step_header(draw, col3, 186, 3, "Cost map")
    rgb = ramp(np.minimum(total, 99) / 99)
    rgb[total == 100] = KEEP_OUT
    cost_tile = Tile(col3, row3, bw, bd, bsk)
    cost_tile.paste(slide, grid_to_image(rgb))
    for t2 in tiles2:
        arrow(draw, (t2.right[0] + 30, t2.right[1]), (cost_tile.left[0] - 22, cost_tile.left[1]))
    label(draw, (col3, row3 + bd + 12), "Sum per cell, 0–99",
          f"red = keep out ({stats['keep_out']:.0%} of the patch)")

    # Colour key under the cost map
    key_x, key_y, key_w = col3, row3 + bd + 82, 300
    key = Image.fromarray(np.repeat(ramp(np.linspace(0, 1, key_w))[None], 12, axis=0)).convert("RGBA")
    slide.alpha_composite(key, (key_x, key_y))
    draw.rectangle([key_x + key_w + 40, key_y, key_x + key_w + 66, key_y + 12], fill=KEEP_OUT)
    draw.text((key_x, key_y + 18), "easy", font=font(16), fill=MUTED)
    draw.text((key_x + key_w, key_y + 18), "hard", font=font(16), fill=MUTED, anchor="ra")
    draw.text((key_x + key_w + 53, key_y + 18), "no go", font=font(16), fill=MUTED, anchor="ma")

    # 4. Route: A* over the cost map, drawn on the orthophoto
    row4 = 690
    step_header(draw, col3, 626, 4, "A* route")
    ortho = Image.open(ROOT / "media/screens/layers/flat/ortofoto.png").convert("RGBA").resize((n, n), Image.BICUBIC)
    no_go = np.zeros((n, n, 4), np.uint8)
    no_go[np.flipud(total == 100)] = KEEP_OUT + (120,)
    ortho.alpha_composite(Image.fromarray(no_go))
    route_draw = ImageDraw.Draw(ortho)
    px = [(x / cell, n - 1 - y / cell) for x, y in points]
    route_draw.line(px, fill=ACCENT + (255,), width=30, joint="curve")
    for (x, y), colour in ((px[0], (255, 255, 255)), (px[-1], ACCENT)):
        route_draw.ellipse([x - 42, y - 42, x + 42, y + 42], fill=colour + (255,), outline=BG + (255,), width=10)
    route_tile = Tile(col3, row4, bw, bd, bsk)
    route_tile.paste(slide, ortho)
    arrow(draw, (key_x + key_w / 2 + 60, key_y + 48), (key_x + key_w / 2 + 60, row4 - 70))
    label(draw, (col3, row4 + bd + 12), "Cheapest path, 8 neighbours",
          "a step costs its length × (1 + cost / 25)")

    # Route numbers and where the route goes next
    px0 = col3 + bsk + bw + 40
    draw.text((px0, row4 - 4), "Rover parking →", font=font(20), fill=MUTED)
    draw.text((px0, row4 + 22), stats["target"], font=font(20, bold=True), fill=INK)
    figures = [
        (f"{stats['length']:.0f} m", f"walk ({stats['straight']:.0f} m straight line)"),
        (f"{stats['minutes']:.0f} min", f"at {WALK_SPEED:g} m/s in a suit"),
        (f"{stats['dose']:.0f} µSv", "dose on the way (model)"),
    ]
    for i, (big, small) in enumerate(figures):
        y = row4 + 70 + i * 66
        draw.text((px0, y), big, font=font(32, bold=True), fill=ACCENT)
        draw.text((px0, y + 38), small, font=font(16), fill=MUTED)
    arrow(draw, (px0, row4 + 290), (px0 + 70, row4 + 290), colour=ACCENT)
    draw.text((px0 + 84, row4 + 290), "HUD and rover", font=font(20, bold=True), fill=INK, anchor="lm")

    # Footer: the formula and the honest caveats
    draw.line([(70, 996), (W - 70, 996)], fill=(255, 255, 255, 40), width=1)
    draw.text((70, 1010), "cost = 70·slope + 15·roughness + 10·dose   (each term 0–1; red cells are never entered)",
              font=font(19, bold=True), fill=INK)
    draw.text((70, 1050), "Weights and limits are our assumptions. Dose is a model from RAD, "
                          "not a measurement at each place.", font=font(16), fill=MUTED)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    slide.convert("RGB").save(OUT, optimize=True)
    print(f"saved {OUT.relative_to(ROOT)}: route {stats['length']:.0f} m, {stats['minutes']:.0f} min, "
          f"{stats['dose']:.1f} uSv, keep out {stats['keep_out']:.0%}, max cost {stats['max_cost']}")


if __name__ == "__main__":
    main()

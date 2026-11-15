"""One helmet HUD frame: the astronaut's view on the Gale terrain, a boulder on the route,
and the route drawn on the ground as it bends around the boulder.

The view is rendered in Isaac Sim from the astronaut's eyes (1.7 m, the same camera as
`sim/run_rover.py --camera astronaut`) on the A* route from the rover parking to the
boxwork field (sim/costmap_slide.py). A boulder ("Desert Rock Base" by bilgehan.korkmaz,
CC BY 4.0, see sim/rock.py) is placed on the route 14 m ahead. The detour is drawn
locally around it: the planner's cost map does not know this rock, which is what a
helmet camera or lidar would have to add. The route is projected with the camera's own
lens and hidden where the terrain is in front of it (depth buffer), then the HUD panels
are drawn in the colours of app/hud.css.

Writes media/screens/hud_frame.png and hud_frame_raw.png. Run with Isaac Sim's python.sh.
"""

import argparse
import json
import math
import sys
from pathlib import Path

from isaacsim import SimulationApp

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--headless", action="store_true", help="run without the Isaac Sim window")
args = parser.parse_args()
W, H = 1920, 1080
simulation_app = SimulationApp({"headless": args.headless, "width": W, "height": H})

import numpy as np
import omni.replicator.core as rep
import omni.usd
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pxr import Gf, UsdGeom

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sim"))
from costmap_slide import compute  # noqa: E402
from rock import ROCK_CREDIT, add_rock  # noqa: E402

TERRAIN = ROOT / "data" / "terrain"
OUT = ROOT / "media" / "screens"
EYE_HEIGHT, FOCAL_MM, APERTURE_MM = 1.7, 18.0, 20.955
WALK_SPEED = 0.8
START_S, ROCK_AHEAD_M, ROCK_SIZE_M = 40.0, 14.0, 2.0
CLEARANCE_M, DETOUR_WIDTH_M = 1.5, 5.0
INK, DIM, CYAN, WARN, OK = (242, 246, 255), (159, 179, 200), (126, 244, 255), (255, 210, 61), (92, 242, 160)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def ground(heights, cell, x, y):
    fx, fy = x / cell, y / cell
    ix, iy = int(fx), int(fy)
    tx, ty = fx - ix, fy - iy
    p = heights[iy:iy + 2, ix:ix + 2]
    return float(p[0, 0] * (1 - tx) * (1 - ty) + p[0, 1] * tx * (1 - ty) + p[1, 0] * (1 - tx) * ty + p[1, 1] * tx * ty)


def smooth_route(points, step=0.5, window_m=6.0):
    """The planner's 4 m cells resampled every step metres and smoothed into a walkable line."""
    pts = np.array(points, float)
    seg = np.hypot(*np.diff(pts, axis=0).T)
    s = np.concatenate([[0], np.cumsum(seg)])
    grid = np.arange(0, s[-1], step)
    line = np.stack([np.interp(grid, s, pts[:, 0]), np.interp(grid, s, pts[:, 1])], axis=1)
    k = int(window_m / step) | 1
    pad = np.pad(line, ((k // 2, k // 2), (0, 0)), mode="edge")
    kernel = np.ones(k) / k
    return np.stack([np.convolve(pad[:, i], kernel, mode="valid") for i in range(2)], axis=1), step


def main():
    meta = json.loads((TERRAIN / "meta.json").read_text())
    heights = np.load(TERRAIN / "heights.npy")
    cell = meta["cell_m"]
    dose_rate = np.load(ROOT / "data" / "layers" / "dose_rate.npy")
    *_, points, _cell, stats, _p = compute()
    line, step = smooth_route(points)

    def at(s):
        return line[min(int(round(s / step)), len(line) - 1)]

    def heading(s):
        d = at(s + 2) - at(s - 2)
        return d / np.linalg.norm(d)

    me = at(START_S)
    forward2 = heading(START_S)
    me_z = ground(heights, cell, *me)
    rock_s = START_S + ROCK_AHEAD_M
    rock_xy = at(rock_s)
    rock_z = ground(heights, cell, *rock_xy)

    omni.usd.get_context().open_stage(str(TERRAIN / "mars_gale.usd"))
    for _ in range(10):
        simulation_app.update()
    stage = omni.usd.get_context().get_stage()
    placed = add_rock(stage, "/World/Rock", rock_xy[0], rock_xy[1], rock_z, size_m=ROCK_SIZE_M, yaw_deg=35.0)
    if placed is None:
        raise SystemExit("sim/assets/desert_rock/Desert_Rock_Base.usdz is missing: see sim/rock.py")
    rock_r, rock_h = placed

    # Detour: the route pushed sideways around the rock, smoothly, to the left of the walking direction
    side = np.array([-forward2[1], forward2[0]])
    clear = rock_r + CLEARANCE_M
    s_path = np.arange(START_S + 1.0, START_S + 70.0, 0.5)
    base = np.array([at(s) for s in s_path])
    bump = clear * np.exp(-((s_path - rock_s) / DETOUR_WIDTH_M) ** 2)
    detour = base + bump[:, None] * side
    extra_m = float(np.sum(np.hypot(*np.diff(detour, axis=0).T)) - np.sum(np.hypot(*np.diff(base, axis=0).T)))

    eye = np.array([*(me + 0.4 * forward2), me_z + EYE_HEIGHT])
    target = eye + np.array([*(10.0 * forward2), -1.0])
    camera = UsdGeom.Camera.Define(stage, "/World/Cameras/Helmet")
    camera.CreateFocalLengthAttr(FOCAL_MM)
    camera.CreateHorizontalApertureAttr(APERTURE_MM)
    camera.CreateVerticalApertureAttr(APERTURE_MM * H / W)
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.05, 20000.0))
    view = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1))
    UsdGeom.Xformable(camera).AddTransformOp().Set(view.GetInverse())

    import omni.kit.viewport.utility as vp
    if not args.headless:
        vp.get_active_viewport().camera_path = "/World/Cameras/Helmet"
    for _ in range(30):
        simulation_app.update()
    product = rep.create.render_product("/World/Cameras/Helmet", (W, H))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    depth = rep.AnnotatorRegistry.get_annotator("distance_to_camera")
    rgb.attach([product])
    depth.attach([product])
    for _ in range(30):
        simulation_app.update()
    rep.orchestrator.step()
    frame = np.asarray(rgb.get_data())[..., :3].copy()
    distance = np.asarray(depth.get_data()).reshape(H, W)
    OUT.mkdir(parents=True, exist_ok=True)
    Image.fromarray(frame).save(OUT / "hud_frame_raw.png")

    # Camera projection, the same pinhole the render used
    fwd = (target - eye) / np.linalg.norm(target - eye)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    fpx = W * FOCAL_MM / APERTURE_MM

    def project(p):
        rel = np.asarray(p, float) - eye
        z = rel @ fwd
        if z <= 0.3:
            return None
        return W / 2 + fpx * (rel @ right) / z, H / 2 - fpx * (rel @ up) / z, float(np.linalg.norm(rel))

    def visible(x, y, dist):
        ix, iy = int(round(x)), int(round(y))
        if not (0 <= ix < W and 0 <= iy < H):
            return False
        d = distance[iy, ix]
        return not np.isfinite(d) or d <= 0 or d > dist - 0.6

    def screen_path(xy, lift=0.06):
        out = []
        for x, y in xy:
            q = project((x, y, ground(heights, cell, x, y) + lift))
            out.append(q if q and visible(*q) else None)
        return out

    hud = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw, gdraw = ImageDraw.Draw(hud), ImageDraw.Draw(glow)

    # The planner's straight line into the rock, faint and dashed
    straight = screen_path(base[(s_path > rock_s - 9) & (s_path < rock_s + 1.5)])
    for i, (a, b) in enumerate(zip(straight, straight[1:])):
        if a and b and i % 4 < 2:
            draw.line([a[:2], b[:2]], fill=DIM + (150,), width=3)

    # The detour, thick cyan with a soft glow, wider near the eye
    path = screen_path(detour)
    for a, b in zip(path, path[1:]):
        if a and b:
            width = max(3, int(36 / max(a[2], 1.0) * 6))
            gdraw.line([a[:2], b[:2]], fill=CYAN + (120,), width=width + 14)
            draw.line([a[:2], b[:2]], fill=CYAN + (235,), width=width)
    # Chevrons every 4 m, pointing along the walk
    for i in range(8, len(detour) - 2, 8):
        a, b = path[i], path[i + 2]
        if a and b:
            d = np.array(b[:2]) - np.array(a[:2])
            n = d / (np.linalg.norm(d) + 1e-6)
            size = max(6, 260 / a[2])
            tip = np.array(a[:2]) + n * size
            left = np.array(a[:2]) + np.array([-n[1], n[0]]) * size * 0.8
            rightp = np.array(a[:2]) - np.array([-n[1], n[0]]) * size * 0.8
            draw.line([tuple(left), tuple(tip), tuple(rightp)], fill=(10, 30, 40, 230), width=max(2, int(size / 5)))

    # Brackets around the rock
    corners = [project((rock_xy[0] + dx, rock_xy[1] + dy, rock_z + dz))
               for dx in (-rock_r, rock_r) for dy in (-rock_r, rock_r) for dz in (0.0, rock_h)]
    corners = [c for c in corners if c]
    if corners:
        xs, ys = [c[0] for c in corners], [c[1] for c in corners]
        x0, y0, x1, y1 = min(xs) - 10, min(ys) - 10, max(xs) + 10, max(ys) + 10
        arm = (x1 - x0) * 0.22
        for (cx, cy, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            draw.line([(cx, cy + sy * arm), (cx, cy), (cx + sx * arm, cy)], fill=WARN + (255,), width=4)
        rock_dist = float(np.linalg.norm(np.array([*rock_xy, rock_z]) - eye))
        draw.text((x1 + 14, y0), "BOULDER", font=ImageFont.truetype(BOLD, 26), fill=WARN + (255,))
        draw.text((x1 + 14, y0 + 32), f"{rock_dist:.0f} m · {ROCK_SIZE_M:.1f} m wide",
                  font=ImageFont.truetype(FONT, 22), fill=INK + (235,))
        draw.text((x1 + 14, y0 + 60), f"pass left, +{extra_m:.1f} m", font=ImageFont.truetype(FONT, 22), fill=CYAN + (255,))

    # Panels, as app/hud.css lays them out
    remaining = stats["length"] - START_S + extra_m
    rate = dose_rate[int(me[1] / cell), int(me[0] / cell)]
    big, mid, small = ImageFont.truetype(BOLD, 40), ImageFont.truetype(BOLD, 30), ImageFont.truetype(FONT, 20)
    label = ImageFont.truetype(BOLD, 17)
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    sd.rounded_rectangle([W / 2 - 330, 28, W / 2 + 330, 128], 18, fill=(0, 0, 0, 120))
    sd.rounded_rectangle([60, H / 2 - 70, 330, H / 2 + 70], 16, fill=(0, 0, 0, 110))
    sd.rounded_rectangle([W - 330, H / 2 - 70, W - 60, H / 2 + 70], 16, fill=(0, 0, 0, 110))
    draw.text((W / 2, 52), "Walk to: Boxwork field, west", font=mid, fill=CYAN + (255,), anchor="mm")
    draw.text((W / 2, 98), f"{remaining:.0f} m  ·  {remaining / WALK_SPEED / 60:.0f} min", font=big,
              fill=INK + (255,), anchor="mm")
    draw.text((84, H / 2 - 48), "O₂ MARGIN", font=label, fill=DIM + (255,))
    draw.text((84, H / 2 - 22), "4 h 26 min", font=mid, fill=OK + (255,))
    draw.text((84, H / 2 + 24), "30 min reserve kept", font=small, fill=DIM + (255,))
    draw.text((W - 84, H / 2 - 48), "DOSE RATE", font=label, fill=DIM + (255,), anchor="ra")
    draw.text((W - 84, H / 2 - 22), f"{rate:.1f} µSv/h", font=mid, fill=INK + (255,), anchor="ra")
    draw.text((W - 84, H / 2 + 24), "model from RAD", font=small, fill=DIM + (255,), anchor="ra")
    draw.text((60, H - 46), f"Gale crater, HiRISE terrain  ·  Boulder: {ROCK_CREDIT}", font=small, fill=DIM + (230,))
    draw.text((W - 60, H - 46), "Marswalk HUD", font=small, fill=DIM + (230,), anchor="ra")

    out = Image.fromarray(frame).convert("RGBA")
    out.alpha_composite(shade)
    out.alpha_composite(glow.filter(ImageFilter.GaussianBlur(9)))
    out.alpha_composite(hud)
    out.convert("RGB").save(OUT / "hud_frame.png")
    print(f"saved media/screens/hud_frame.png: rock {ROCK_AHEAD_M:.0f} m ahead, r {rock_r:.1f} m, h {rock_h:.1f} m, "
          f"detour +{extra_m:.1f} m, {sum(1 for q in path if q)} of {len(path)} route points visible")
    simulation_app.close()


main()

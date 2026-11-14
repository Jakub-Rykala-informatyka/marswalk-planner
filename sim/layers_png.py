"""Export each NASA layer as a transparent PNG, seen from the same oblique view as layers_oblique.png.

Each layer is projected onto the plane it has in the stack (same camera, same
floor heights as sim/layers_view.py), so the PNG has the layer's real perspective
and no background. The canvas is sized to the whole projected square: nothing
is cut off. Plain Python with numpy and Pillow; no Isaac Sim needed.

Writes media/screens/layers/<layer>.png. Run after sim/layers_view.py has set
the same constants (FLOOR_GAP, FIRST_FLOOR, camera offsets).
"""

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
LAYERS = ROOT / "data" / "layers"
OUT = ROOT / "media" / "screens" / "layers"

# Same constants as sim/layers_view.py
FLOOR_GAP = 380.0
FIRST_FLOOR = 180.0
ORDER = ["slope", "roughness", "sky_view", "dose_shelter", "dose_rate"]
W, H = 1920, 1080
FOCAL_PX = 30.0 / 20.955 * W  # Isaac camera: 30 mm focal length, 20.955 mm horizontal aperture
CX, CY = W / 2, H / 2
PAD = 24


def look_at(eye, centre, up=(0.0, 0.0, 1.0)):
    forward = centre - eye
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    up2 = np.cross(right, forward)
    return right, up2, forward


def project(points, eye, right, up2, forward):
    """World points to image pixels, the way the Isaac camera draws them."""
    rel = points - eye
    x, y, z = rel @ right, rel @ up2, rel @ forward
    return np.stack([CX + FOCAL_PX * x / z, CY - FOCAL_PX * y / z], axis=1)


def homography(src, dst):
    """3x3 matrix H with dst ~ H src, from four point pairs."""
    rows, rhs = [], []
    for (x, y), (u, v) in zip(src, dst):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rhs.append(u)
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        rhs.append(v)
    h = np.linalg.solve(np.array(rows, float), np.array(rhs, float))
    return np.append(h, 1.0).reshape(3, 3)


def main():
    meta = json.loads((ROOT / "data" / "terrain" / "meta.json").read_text())
    size = meta["size_m"]
    top = float(np.load(ROOT / "data" / "terrain" / "heights.npy").max())
    centre = np.array([size / 2, size / 2, top + FIRST_FLOOR + 2 * FLOOR_GAP])
    eye = centre + np.array([-size * 2.3, -size * 2.6, size * 1.6])
    right, up2, forward = look_at(eye, centre)
    OUT.mkdir(parents=True, exist_ok=True)

    for i, name in enumerate(ORDER):
        height = top + FIRST_FLOOR + i * FLOOR_GAP
        corners = np.array([[0, 0, height], [size, 0, height], [size, size, height], [0, size, height]], float)
        quad = project(corners, eye, right, up2, forward)  # image corners in the stack view

        # Texture corners: the layer PNG has row 0 at the north edge, so world south is the bottom row
        tex = Image.open(LAYERS / f"{name}.png").convert("RGBA")
        tw, th = tex.size
        tex_corners = np.array([[0, th], [tw, th], [tw, 0], [0, 0]], float)  # SW, SE, NE, NW

        # Canvas: the bounding box of the projected square, with a margin
        x0, y0 = np.floor(quad.min(axis=0)) - PAD
        x1, y1 = np.ceil(quad.max(axis=0)) + PAD
        canvas_size = (int(x1 - x0), int(y1 - y0))
        shifted = quad - [x0, y0]

        # PIL maps output pixels back to texture pixels: invert texture -> canvas
        to_canvas = homography(tex_corners, shifted)
        back = np.linalg.inv(to_canvas)
        coeffs = tuple((back / back[2, 2]).flatten()[:8])
        out = tex.transform(canvas_size, Image.PERSPECTIVE, coeffs, Image.BICUBIC)
        out.save(OUT / f"{name}.png")
        print(f"{name}: {canvas_size[0]} x {canvas_size[1]} px, transparent background")

    # The terrain texture on its own, as a plain top-down map
    terrain = Image.open(ROOT / "data" / "terrain" / "texture_hires.jpg" if (ROOT / "data" / "terrain" / "texture_hires.jpg").exists()
                         else ROOT / "data" / "terrain" / "texture.jpg").convert("RGBA")
    terrain.save(OUT / "terrain.png")
    print(f"terrain: {terrain.size[0]} x {terrain.size[1]} px, top-down")


if __name__ == "__main__":
    main()

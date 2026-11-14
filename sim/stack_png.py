"""One transparent PNG with the whole stack seen from the oblique view.

The orthophoto sits on the ground at the bottom, and each NASA layer sits on its
own floor above it, the same camera and floor heights as sim/layers_view.py.
Writes media/screens/layers/stack.png. Plain Python: numpy and Pillow.
"""

import json

import numpy as np
from PIL import Image

import layers_png as lp

ROOT = lp.ROOT
OUT = ROOT / "media" / "screens" / "layers"


def warp(texture, quad_world_corners, eye, right, up2, forward, tex_size):
    """Project a texture onto a world quad: returns the RGBA image and its top-left offset."""
    quad = lp.project(quad_world_corners, eye, right, up2, forward)
    tw, th = tex_size
    tex_corners = np.array([[0, th], [tw, th], [tw, 0], [0, 0]], float)
    x0, y0 = np.floor(quad.min(axis=0)) - lp.PAD
    x1, y1 = np.ceil(quad.max(axis=0)) + lp.PAD
    canvas = (int(x1 - x0), int(y1 - y0))
    back = np.linalg.inv(lp.homography(tex_corners, quad - [x0, y0]))
    coeffs = tuple((back / back[2, 2]).flatten()[:8])
    out = texture.transform(canvas, Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    return out, (int(x0), int(y0))


def main():
    meta = json.loads((ROOT / "data" / "terrain" / "meta.json").read_text())
    size = meta["size_m"]
    top = float(np.load(ROOT / "data" / "terrain" / "heights.npy").max())
    centre = np.array([size / 2, size / 2, top + lp.FIRST_FLOOR + 2 * lp.FLOOR_GAP])
    eye = centre + np.array([-size * 2.3, -size * 2.6, size * 1.6])
    right, up2, forward = lp.look_at(eye, centre)

    def square(height):
        return np.array([[0, 0, height], [size, 0, height], [size, size, height], [0, size, height]], float)

    # (texture, floor height), bottom first: orthophoto on the ground, then the five layers
    pieces = [(ROOT / "media/screens/layers/flat/ortofoto.png", 0.0)]
    for i, name in enumerate(lp.ORDER):
        pieces.append((ROOT / "data" / "layers" / f"{name}.png", top + lp.FIRST_FLOOR + i * lp.FLOOR_GAP))

    placed = []
    for path, height in pieces:
        tex = Image.open(path).convert("RGBA")
        img, offset = warp(tex, square(height), eye, right, up2, forward, tex.size)
        placed.append((img, offset))

    left = min(o[0] for _, o in placed)
    upper = min(o[1] for _, o in placed)
    right_edge = max(o[0] + i.size[0] for i, o in placed)
    lower = max(o[1] + i.size[1] for i, o in placed)
    canvas = Image.new("RGBA", (right_edge - left, lower - upper), (0, 0, 0, 0))
    for img, (x, y) in placed:  # bottom first, so upper floors sit over lower ones
        canvas.alpha_composite(img, (x - left, y - upper))

    OUT.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT / "stack.png", optimize=True)
    print(f"stack.png {canvas.size[0]} x {canvas.size[1]} px, transparent background")


if __name__ == "__main__":
    main()

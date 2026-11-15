"""Slide picture of what a cost map is: the cost factors stacked over the HiRISE image.

Bottom: the grey HiRISE image of the patch, for orientation. Above it, one floor per
cost factor from ros/cost_model.py in the cost map's colours, each on its own scale
(white = none of it, black = the most of it, keep out black), heaviest on top: dose (10),
sand (10), roughness (15), slope (70). Adding the floors times their weights gives the
cost map; the slide states the weights. Same oblique camera and floor heights as
sim/stack_png.py. Writes media/slides/cost_stack.png with a transparent background.
Plain Python: numpy and Pillow.
"""

import json

import numpy as np
from PIL import Image

import layers_png as lp
from costmap_slide import compute
from stack_png import warp

ROOT = lp.ROOT
OUT = ROOT / "media" / "slides" / "cost_stack.png"
FACTORS = ["dose", "sand", "roughness", "slope"]  # bottom to top, by weight


def grey_image(share):
    """0 (none of the factor) -> white, 1 (the most of it) -> black, north up."""
    g = (1 - np.clip(share, 0, 1)) * 255
    return Image.fromarray(np.flipud(g.astype(np.uint8))).convert("RGBA")


def main():
    raw, terms, total, *_rest, p = compute()
    meta = json.loads((ROOT / "data" / "terrain" / "meta.json").read_text())
    size = meta["size_m"]
    top = float(np.load(ROOT / "data" / "terrain" / "heights.npy").max())
    centre = np.array([size / 2, size / 2, top + lp.FIRST_FLOOR + 1.5 * lp.FLOOR_GAP])
    eye = centre + np.array([-size * 2.3, -size * 2.6, size * 1.6])
    right, up2, forward = lp.look_at(eye, centre)

    def square(height):
        return np.array([[0, 0, height], [size, 0, height], [size, size, height], [0, size, height]], float)

    hirise = Image.open(ROOT / "data" / "terrain" / "texture_hires.jpg").getchannel("R").convert("RGBA")
    hirise.thumbnail((1024, 1024))
    pieces = [(hirise, 0.0)]
    for i, name in enumerate(FACTORS):
        share = terms[name] / p[f"{name}_weight"]
        if name == "slope":
            share = np.where(raw["slope"] >= p["max_slope_deg"], 1.0, share)  # keep out drawn black
        pieces.append((grey_image(share), top + lp.FIRST_FLOOR + i * lp.FLOOR_GAP))

    placed = [warp(texture, square(height), eye, right, up2, forward, texture.size) for texture, height in pieces]
    left = min(o[0] for _, o in placed)
    upper = min(o[1] for _, o in placed)
    canvas = Image.new("RGBA", (max(o[0] + i.size[0] for i, o in placed) - left,
                                max(o[1] + i.size[1] for i, o in placed) - upper), (0, 0, 0, 0))
    for image, (x, y) in placed:
        canvas.alpha_composite(image, (x - left, y - upper))
    canvas.save(OUT, optimize=True)
    print(f"saved {OUT.relative_to(ROOT)}: {canvas.size[0]} x {canvas.size[1]} px, "
          f"floors bottom to top: HiRISE, {', '.join(FACTORS)}")


if __name__ == "__main__":
    main()

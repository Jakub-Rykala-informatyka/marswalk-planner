"""Flat top-down PNGs: the orthophoto, each NASA layer, and all layers laid over the orthophoto.

Writes to media/screens/layers/flat/:
  ortofoto.png   the 25 cm HiRISE orthophoto of the patch, top-down
  overlay.png    the orthophoto with every layer blended on top at its own opacity
Each layer is also in flat/<name>.png, aligned with the orthophoto.
Plain Python with Pillow; no Isaac Sim needed.
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
LAYERS = ROOT / "data" / "layers"
TERRAIN = ROOT / "data" / "terrain"
OUT = ROOT / "media" / "screens" / "layers" / "flat"
SIZE = 2048

# Blend order from the ground up, and how strongly each layer shows on the photo
BLEND = [
    ("slope", 0.40),
    ("roughness", 0.30),
    ("sky_view", 0.30),
    ("dose_shelter", 1.0),  # already transparent where the dose is not reduced
    ("dose_rate", 0.25),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = TERRAIN / "texture_hires.jpg" if (TERRAIN / "texture_hires.jpg").exists() else TERRAIN / "texture.jpg"
    ortho = Image.open(source).convert("RGBA").resize((SIZE, SIZE), Image.LANCZOS)
    ortho.save(OUT / "ortofoto.png", optimize=True)

    canvas = ortho.copy()
    for name, strength in BLEND:
        layer = Image.open(LAYERS / f"{name}.png").convert("RGBA").resize((SIZE, SIZE), Image.BICUBIC)
        layer.save(OUT / f"{name}.png", optimize=True)
        if name == "dose_shelter":
            canvas.alpha_composite(layer)  # keeps the layer's own alpha
            continue
        # Layers are grey-scale, so take their brightness as the layer and mix it over the photo
        alpha = Image.new("L", layer.size, int(255 * strength))
        layer.putalpha(alpha)
        canvas.alpha_composite(layer)
        print(f"{name}: blended at {strength:.0%}")

    canvas.convert("RGB").save(OUT / "overlay.png", optimize=True)
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()

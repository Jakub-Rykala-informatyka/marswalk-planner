"""Cut a small terrain patch out of a HiRISE DTM and its orthoimage.

Needs only numpy and Pillow (with JPEG 2000), so it runs with Isaac Sim's
python.sh without starting the simulator.

  overview  -> data/preview/*.png, to pick the patch by eye
  crop      -> data/terrain/{heights.npy, texture.jpg, meta.json}
  hires     -> data/terrain/texture_hires.jpg for the same patch, from the
               25 cm orthoimage (large, kept out of the repository)

Pixel coordinates are (line, sample) of the full DTM, line 0 at the north edge.
Local coordinates of the patch: metres, origin in the south-west corner,
x east, y north, z up (height above the lowest point of the patch).
"""

import argparse
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DTM = RAW / "DTEEC_001488_1750_001752_1750_U02.IMG"
ORTHO = RAW / "PSP_001752_1750_RED_C_01_ORTHO.JP2"
ORTHO_HIRES = RAW / "PSP_001752_1750_RED_A_01_ORTHO.JP2"

# Elevations below this are the PDS missing-data constant, not terrain
NODATA_BELOW = -1e30
# Mars-like tint for the grayscale HiRISE RED band (colour is not measured data)
MARS_TINT = np.array([1.00, 0.66, 0.42])


def label_keys(path):
    """Return a reader of PDS3 label keywords from the head of a label or .IMG file."""
    head = path.read_bytes()[:20000].decode("latin-1")

    def key(name, cast=float):
        m = re.search(rf"^\s*{name}\s*=\s*([^\s<]+)", head, re.M)
        return cast(m.group(1))

    return key


def read_label(path):
    key = label_keys(path)
    return {
        "record_bytes": key("RECORD_BYTES", int),
        "image_record": key(r"\^IMAGE", int),
        "lines": key("LINES", int),
        "samples": key("LINE_SAMPLES", int),
        "map_scale": key("MAP_SCALE"),
        "map_resolution": key("MAP_RESOLUTION"),
        "center_lon": key("CENTER_LONGITUDE"),
        "line_offset": key("LINE_PROJECTION_OFFSET"),
        "sample_offset": key("SAMPLE_PROJECTION_OFFSET"),
    }


def open_dtm():
    label = read_label(DTM)
    offset = (label["image_record"] - 1) * label["record_bytes"]
    dtm = np.memmap(DTM, dtype="<f4", mode="r", offset=offset,
                    shape=(label["lines"], label["samples"]))
    return dtm, label


def hillshade(z, cell, azimuth_deg=315.0, altitude_deg=35.0):
    dy, dx = np.gradient(z, cell)
    az, alt = np.radians(azimuth_deg), np.radians(altitude_deg)
    slope = np.arctan(np.hypot(dx, dy))
    aspect = np.arctan2(dy, -dx)
    shade = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(shade, 0, 1)


def overview(step):
    dtm, label = open_dtm()
    z = np.array(dtm[::step, ::step])
    valid = z > NODATA_BELOW
    z[~valid] = np.nan
    out = ROOT / "data" / "preview"
    out.mkdir(parents=True, exist_ok=True)

    shade = hillshade(np.nan_to_num(z, nan=np.nanmin(z)), label["map_scale"] * step)
    shade[~valid] = 0
    Image.fromarray((shade * 255).astype(np.uint8)).save(out / "dtm_hillshade.png")

    lo, hi = np.nanpercentile(z, [1, 99])
    elev = np.clip((z - lo) / (hi - lo), 0, 1)
    elev[~valid] = 0
    Image.fromarray((elev * 255).astype(np.uint8)).save(out / "dtm_elevation.png")

    ortho = Image.open(ORTHO)
    ortho.reduce = int(np.log2(step))
    ortho.load()
    ortho.convert("L").save(out / "ortho.png")

    print(f"DTM {label['lines']} x {label['samples']} px, {label['map_scale']:.4f} m/px")
    print(f"elevation {np.nanmin(z):.0f} .. {np.nanmax(z):.0f} m, valid {valid.mean():.0%}")
    print(f"preview step {step} px -> {z.shape}, saved in {out}")


def tint(gray_image):
    """Stretch the contrast of a grayscale image and give it the Mars tint."""
    gray = np.asarray(gray_image, dtype=np.float32)
    lo, hi = np.percentile(gray[::4, ::4], [0.5, 99.5])
    gray = np.clip((gray - lo) / (hi - lo), 0, 1)
    return Image.fromarray((gray[..., None] * MARS_TINT * 255).astype(np.uint8))


def hires():
    """Cut the patch recorded in meta.json out of the 25 cm orthoimage."""
    out = ROOT / "data" / "terrain"
    patch = json.loads((out / "meta.json").read_text())["crop_px"]
    _, dtm = open_dtm()
    key = label_keys(ORTHO_HIRES.with_suffix(".LBL"))
    ratio = dtm["map_scale"] / key("MAP_SCALE")
    # Same map projection, so pixel grids differ only by scale and offset
    top = round(key("LINE_PROJECTION_OFFSET") - (dtm["line_offset"] - patch["line"]) * ratio)
    left = round(key("SAMPLE_PROJECTION_OFFSET") + (patch["sample"] - dtm["sample_offset"]) * ratio)
    side = round(patch["size"] * ratio)
    ortho = Image.open(ORTHO_HIRES).crop((left, top, left + side, top + side)).convert("L")
    tint(ortho).save(out / "texture_hires.jpg", quality=90)
    print(f"texture_hires.jpg: {side} x {side} px, {key('MAP_SCALE'):.3f} m/px")


def crop(line, sample, size, step):
    """Cut size x size pixels with the north-west corner at (line, sample)."""
    dtm, label = open_dtm()
    z = np.array(dtm[line:line + size + 1:step, sample:sample + size + 1:step], dtype=np.float32)
    if (z < NODATA_BELOW).any():
        raise SystemExit("patch contains missing DTM data, pick another place")

    z_min = float(z.min())
    heights = np.flipud(z - z_min)  # row 0 = south edge, so index [iy, ix] matches y north, x east
    scale = label["map_scale"]
    out = ROOT / "data" / "terrain"
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "heights.npy", heights)

    ortho = Image.open(ORTHO).crop((sample, line, sample + size, line + size)).convert("L")
    tint(ortho).save(out / "texture.jpg", quality=92)

    # Projected metres -> degrees, equirectangular with latitude of true scale 0
    lat_north = (label["line_offset"] - line) / label["map_resolution"]
    lon_west = label["center_lon"] + (sample - label["sample_offset"]) / label["map_resolution"]
    span_deg = size / label["map_resolution"]
    meta = {
        "source_dtm": DTM.name,
        "source_ortho": ORTHO.name,
        "crop_px": {"line": line, "sample": sample, "size": size, "step": step},
        "cell_m": scale * step,
        "size_m": scale * size,
        "grid": list(heights.shape),
        "elevation_of_z0_m": z_min,
        "relief_m": float(heights.max()),
        "bounds_deg": {
            "north": lat_north, "south": lat_north - span_deg,
            "west": lon_west, "east": lon_west + span_deg,
        },
        "frame": "local metres, origin south-west corner, x east, y north, z up",
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("overview")
    p.add_argument("--step", type=int, default=8, help="downsampling, a power of two")
    p = sub.add_parser("crop")
    p.add_argument("--line", type=int, required=True, help="north edge of the patch, px")
    p.add_argument("--sample", type=int, required=True, help="west edge of the patch, px")
    p.add_argument("--size", type=int, default=2048, help="patch side, px (about 1 m each)")
    p.add_argument("--step", type=int, default=2, help="keep every n-th height sample")
    sub.add_parser("hires")
    args = parser.parse_args()
    if args.cmd == "overview":
        overview(args.step)
    elif args.cmd == "hires":
        hires()
    else:
        crop(args.line, args.sample, args.size, args.step)

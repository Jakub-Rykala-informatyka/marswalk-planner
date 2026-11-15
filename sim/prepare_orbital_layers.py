"""THEMIS and CRISM layers for the patch: loose sand from night-time temperature, minerals from CRISM.

Run after `sim/prepare_terrain.py layers` (which rewrites data/meta.json). Inputs in data/raw/:

- THEMIS night IR controlled mosaic, 100 m (Mars Odyssey), one NASA Mars Trek tile:
  curl -o data/raw/THEMIS_NightIR_100m_z9_r269_c902.png https://trek.nasa.gov/tiles/Mars/EQ/THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018/1.0.0/default/default028mm/9/269/902.png
- CRISM MTRDR FRT0001BBA1 refined spectral summary parameters, 18 m (MRO), PDS Geosciences Node:
  https://pds-geosciences.wustl.edu/mro/mro-m-crism-5-rdr-mptargeted-v1/mrocr_4001/mtrdr/2010/2010_310/frt0001bba1/frt0001bba1_07_sr165j_mtr3.{img,lbl}

Writes to data/layers/ and adds the layers to data/meta.json:
- themis_night: night IR brightness of the mosaic (relative, 0..255). Warm at night means
  rock that holds heat (high thermal inertia), cold means loose sand or dust.
- sand: 0..1, how much colder than the patch's median the ground is at night: a proxy for
  loose sand. Relative within this patch and only 81 m sharp, so it is background.
- hydration (BD1900_2) and sulfate (SINDEX2): CRISM band depths for water bound in minerals
  and for polyhydrated sulfates, the minerals of the sulfate unit of lower Mount Sharp.

CRISM's map position is off by a few hundred metres against HiRISE, so the script shifts it
to where its 770 nm reflectance matches the HiRISE image best, and records that shift.
"""

import json
import re
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "layers"
THEMIS_TILE = RAW / "THEMIS_NightIR_100m_z9_r269_c902.png"
THEMIS_Z, THEMIS_ROW, THEMIS_COL = 9, 269, 902  # Mars Trek equirectangular tiles: 2 x 1 at level 0, 256 px each
CRISM = RAW / "FRT0001BBA1_07_SR165J_MTR3"
CRISM_SEARCH_PX = 40  # how far to look for the registration shift, in CRISM pixels (18 m)
# Band depth shown as clear .. full colour: below the first value is noise in a CRISM summary parameter
MINERALS = {"hydration": ("BD1900_2", 0.005, 0.03, (70, 150, 255)),
            "sulfate": ("SINDEX2", 0.01, 0.04, (190, 110, 255))}


def patch_grid(meta):
    """Latitude and longitude of every sample of the patch grid (rows south to north)."""
    b, n = meta["bounds_deg"], meta["grid"][0]
    lat = b["south"] + np.arange(n) / (n - 1) * (b["north"] - b["south"])
    lon = b["west"] + np.arange(n) / (n - 1) * (b["east"] - b["west"])
    return np.meshgrid(lat, lon, indexing="ij")


def themis(lat, lon):
    tile = np.asarray(Image.open(THEMIS_TILE).convert("L"), np.float32)
    deg = 180.0 / (256 * 2 ** THEMIS_Z)
    lon0, lat0 = -180.0 + THEMIS_COL * 256 * deg, 90.0 - THEMIS_ROW * 256 * deg
    rows, cols = (lat0 - lat) / deg - 0.5, (lon - lon0) / deg - 0.5  # pixel centres
    return map_coordinates(tile, [rows, cols], order=1, mode="nearest"), deg * 59270  # m per px at the equator


def crism_cube():
    label = (CRISM.with_suffix(".LBL")).read_text(encoding="latin-1")
    key = lambda k: float(re.search(rf"^\s*{k}\s*=\s*([-\d.E+]+)", label, re.M).group(1))
    shape = int(key("BANDS")), int(key("LINES")), int(key("LINE_SAMPLES"))
    names = [s.strip().strip('"') for s in re.search(r"BAND_NAME\s*=\s*\((.*?)\)", label, re.S).group(1).split(",")]
    cube = np.memmap(CRISM.with_suffix(".IMG"), dtype="<f4", mode="r").reshape(shape)
    projection = key("MAP_RESOLUTION"), key("LINE_PROJECTION_OFFSET"), key("SAMPLE_PROJECTION_OFFSET")
    return cube, names, projection


def crism_shift(cube, names, projection, meta):
    """Pixel shift (lines, samples) that best lines CRISM's 770 nm reflectance up with HiRISE."""
    res, line_off, sample_off = projection
    b = meta["bounds_deg"]
    top, left = line_off - b["north"] * res - 1, sample_off + b["west"] * res - 1
    n = int(round((b["north"] - b["south"]) * res))
    r770 = np.array(cube[names.index("R770")])
    hirise = np.asarray(Image.open(ROOT / "data" / "terrain" / "texture.jpg").convert("L"), np.float32)
    hirise = np.asarray(Image.fromarray(hirise).resize((n, n), Image.BOX)).ravel()
    best = (-1.0, 0, 0)
    for dy in range(-CRISM_SEARCH_PX, CRISM_SEARCH_PX + 1):
        for dx in range(-CRISM_SEARCH_PX, CRISM_SEARCH_PX + 1):
            y, x = int(round(top)) + dy, int(round(left)) + dx
            window = r770[y:y + n, x:x + n]
            if y < 0 or x < 0 or window.shape != (n, n) or np.any(window > 1e30):
                continue
            best = max(best, (float(np.corrcoef(window.ravel(), hirise)[0, 1]), dy, dx))
    return best


def crism(lat, lon, cube, names, projection, shift):
    res, line_off, sample_off = projection
    _, dy, dx = shift
    rows = line_off - lat * res - 1 + dy  # 1-based PDS lines and samples -> 0-based array index
    cols = sample_off + lon * res - 1 + dx
    out = {}
    for name, (band, *_rest) in MINERALS.items():
        values = np.array(cube[names.index(band)], np.float32)
        values[values > 1e30] = np.nan
        out[name] = map_coordinates(values, [rows, cols], order=1, mode="nearest", cval=np.nan)
    return out


def overlay(share, colour, alpha_max=210):
    image = np.zeros((*share.shape, 4), np.uint8)
    image[..., :3] = colour
    image[..., 3] = (np.nan_to_num(share) * alpha_max).astype(np.uint8)
    return Image.fromarray(np.flipud(image))


def main():
    meta_path = ROOT / "data" / "meta.json"
    meta = json.loads(meta_path.read_text())
    lat, lon = patch_grid(meta)

    night, themis_m = themis(lat, lon)
    median, cold = np.percentile(night, [50, 5])
    sand = np.clip((median - night) / (median - cold), 0, 1).astype(np.float32)

    cube, names, projection = crism_cube()
    shift = crism_shift(cube, names, projection, meta)
    minerals = crism(lat, lon, cube, names, projection, shift)

    np.save(OUT / "themis_night.npy", night.astype(np.float32))
    Image.fromarray(np.flipud(night).astype(np.uint8)).save(OUT / "themis_night.png")
    np.save(OUT / "sand.npy", sand)
    overlay(sand, (235, 190, 90)).save(OUT / "sand.png")
    meta["layers"]["themis_night"] = {
        "unit": "relative night IR brightness (0..255)", "png_black": 0.0, "png_white": 255.0,
        "min": float(night.min()), "max": float(night.max()),
        "source": "Mars Odyssey THEMIS night IR controlled mosaic, 100 m (NASA Mars Trek, "
                  "THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018)", "pixel_m": round(themis_m)}
    meta["layers"]["sand"] = {
        "unit": "share 0..1", "png": "amber, clear at 0, strongest at 1",
        "min": float(sand.min()), "max": float(sand.max()),
        "formula": f"(median - night) / (median - 5th percentile), night median {median:.0f}, 5th percentile {cold:.0f}",
        "limits": "relative within this patch; THEMIS pixels are about 80 m, so it marks sandy areas, not single dunes"}
    for name, (band, lo, hi, colour) in MINERALS.items():
        values = minerals[name]
        np.save(OUT / f"{name}.npy", values)
        overlay(np.clip((values - lo) / (hi - lo), 0, 1), colour).save(OUT / f"{name}.png")
        meta["layers"][name] = {
            "unit": f"CRISM band depth {band}", "png": f"clear below {lo}, full colour at {hi}",
            "min": float(np.nanmin(values)), "max": float(np.nanmax(values)),
            "share_above_clear": float(np.nanmean(values > lo)),
            "source": "MRO CRISM MTRDR FRT0001BBA1 refined summary parameters (SR165J), 18 m"}
    meta["crism_registration"] = {
        "shift_px": {"lines": shift[1], "samples": shift[2]},
        "shift_m": {"south": shift[1] * 18, "east": shift[2] * 18},
        "match": f"R770 against the HiRISE image, correlation {shift[0]:.2f}"}
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    print(f"THEMIS night IR {night.min():.0f}..{night.max():.0f} (about {themis_m:.0f} m/px), "
          f"sand share above 0.5: {np.mean(sand > 0.5):.0%}")
    print(f"CRISM shift {shift[1]} lines, {shift[2]} samples (corr {shift[0]:.2f})")
    for name, (band, lo, hi, _) in MINERALS.items():
        v = minerals[name]
        print(f"{name} ({band}): {np.nanmin(v):.4f}..{np.nanmax(v):.4f}, p50 {np.nanpercentile(v, 50):.4f}, "
              f"p99 {np.nanpercentile(v, 99):.4f}, above {lo}: {np.nanmean(v > lo):.0%}")


if __name__ == "__main__":
    main()

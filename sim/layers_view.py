"""Render the terrain with the NASA layers stacked above it, from an oblique view.

Each layer (slope, roughness, sky view, dose, shelter) is a flat grey-scale or
coloured plane floating above the Gale terrain, one floor per layer, so the
layers visibly sit on the same ground. Run with Isaac Sim's python.sh; writes
media/screens/layers_oblique.png (kept as a slide image).

The terrain comes from data/terrain/mars_gale.usd (run build_scene.py first).
"""

import argparse
import json
from pathlib import Path

from isaacsim import SimulationApp

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--headless", action="store_true", help="run without the Isaac Sim window")
args = parser.parse_args()

simulation_app = SimulationApp({"headless": args.headless, "width": 1920, "height": 1080})

import numpy as np
import omni.replicator.core as rep
import omni.usd
from PIL import Image
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade, Vt

ROOT = Path(__file__).resolve().parents[1]
TERRAIN_USD = ROOT / "data" / "terrain" / "mars_gale.usd"
LAYERS = ROOT / "data" / "layers"
OUT = ROOT / "media" / "screens" / "layers_oblique.png"

FLOOR_GAP = 380.0  # m between one layer floor and the next
FIRST_FLOOR = 180.0  # m above the highest ground
# (file, title) from bottom to top
FLOORS = [
    ("slope", "Slope"),
    ("roughness", "Roughness"),
    ("sky_view", "Open sky"),
    ("dose_shelter", "Radiation shelter"),
    ("dose_rate", "Dose rate"),
]


def add_floor(stage, path, size, height, texture):
    """A flat square at the given height, the size of the patch, with a texture on it."""
    half = size / 2
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(0, 0, height), Gf.Vec3f(size, 0, height),
                                         Gf.Vec3f(size, size, height), Gf.Vec3f(0, size, height)]))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray([4]))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray([0, 1, 2, 3]))
    mesh.CreateDoubleSidedAttr(True)
    mesh.CreateNormalsAttr(Vt.Vec3fArray([Gf.Vec3f(0, 0, 1)] * 4))
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    st = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
    st.Set(Vt.Vec2fArray([Gf.Vec2f(0, 0), Gf.Vec2f(1, 0), Gf.Vec2f(1, 1), Gf.Vec2f(0, 1)]))

    material = UsdShade.Material.Define(stage, f"{path}_mat")
    shader = UsdShade.Shader.Define(stage, f"{path}_mat/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.92)
    reader = UsdShade.Shader.Define(stage, f"{path}_mat/St")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    tex = UsdShade.Shader.Define(stage, f"{path}_mat/Tex")
    tex.CreateIdAttr("UsdUVTexture")
    tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(str(texture)))
    tex.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
    tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(tex.ConnectableAPI(), "rgb")
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).ConnectToSource(tex.ConnectableAPI(), "a")
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    return mesh


def main():
    meta = json.loads((ROOT / "data" / "terrain" / "meta.json").read_text())
    size = meta["size_m"]
    heights = np.load(ROOT / "data" / "terrain" / "heights.npy")
    top = float(heights.max())

    omni.usd.get_context().open_stage(str(TERRAIN_USD))
    for _ in range(10):
        simulation_app.update()
    stage = omni.usd.get_context().get_stage()

    UsdLux.DomeLight.Define(stage, "/World/LayerSky").CreateIntensityAttr(600)
    sun = UsdLux.DistantLight.Define(stage, "/World/LayerSun")
    sun.CreateIntensityAttr(2000)
    UsdGeom.Xformable(sun).AddRotateXYZOp().Set(Gf.Vec3f(50.0, 0.0, 30.0))

    # Floors and their labels, each floor a little above the one below
    labels = []
    for i, (name, title) in enumerate(FLOORS):
        height = top + FIRST_FLOOR + i * FLOOR_GAP
        add_floor(stage, f"/World/Floor_{name}", size, height, LAYERS / f"{name}.png")
        labels.append((title, height))
        # A thin pole from the ground to each floor, so the stack reads as one column per place
    for i in range(len(FLOORS)):
        pole = UsdGeom.Cylinder.Define(stage, f"/World/Pole_{i}")
        pole.CreateRadiusAttr(4.0)
        pole.CreateHeightAttr(FIRST_FLOOR + i * FLOOR_GAP)
        pole.CreateAxisAttr("Z")
        pole.CreateDisplayColorAttr([Gf.Vec3f(0.9, 0.9, 0.9)])
        UsdGeom.Xformable(pole).AddTranslateOp().Set(Gf.Vec3d(size * 0.02, size * 0.02, top))

    # Oblique camera: from the south-west, looking across the stack to the north-east
    camera = UsdGeom.Camera.Define(stage, "/World/Cameras/Oblique")
    camera.CreateFocalLengthAttr(30.0)
    camera.CreateClippingRangeAttr(Gf.Vec2f(10.0, 40000.0))
    centre = Gf.Vec3d(size / 2, size / 2, top + FIRST_FLOOR + 2 * FLOOR_GAP)
    eye = centre + Gf.Vec3d(-size * 2.3, -size * 2.6, size * 1.6)
    view = Gf.Matrix4d().SetLookAt(eye, centre, Gf.Vec3d(0, 0, 1))
    UsdGeom.Xformable(camera).AddTransformOp().Set(view.GetInverse())

    import omni.kit.viewport.utility as vp
    viewport = vp.get_active_viewport()
    viewport.camera_path = "/World/Cameras/Oblique"
    for _ in range(30):
        simulation_app.update()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    product = rep.create.render_product("/World/Cameras/Oblique", (1920, 1080))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach([product])
    for _ in range(20):
        simulation_app.update()
    rep.orchestrator.step()
    Image.fromarray(rgb.get_data()[..., :3]).save(OUT)
    print(f"saved {OUT}")
    rgb.detach()
    product.destroy()
    simulation_app.close()


main()

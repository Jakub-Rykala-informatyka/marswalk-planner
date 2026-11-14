"""Each NASA layer draped on the curved Gale terrain, rendered in Isaac Sim, transparent background.

The terrain mesh (data/terrain/mars_gale.usd) keeps its relief; only its texture is
swapped for each layer. The background is removed with the depth buffer (no terrain
hit = transparent), so the PNGs have an alpha channel and no sky.
Writes media/screens/layers/draped/<name>.png. Run with Isaac Sim's python.sh.
"""

from pathlib import Path

from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": False, "width": 1600, "height": 1200})

import numpy as np
import omni.replicator.core as rep
import omni.usd
from PIL import Image
from pxr import Gf, Sdf, UsdGeom, UsdLux, UsdShade

ROOT = Path(__file__).resolve().parents[1]
TERRAIN = ROOT / "data" / "terrain" / "mars_gale.usd"
LAYERS = ROOT / "data" / "layers"
OUT = ROOT / "media" / "screens" / "layers" / "draped"
MAPS = {
    "ortofoto": ROOT / "media/screens/layers/flat/ortofoto.png",
    "slope": LAYERS / "slope.png",
    "roughness": LAYERS / "roughness.png",
    "sky_view": LAYERS / "sky_view.png",
    "dose_shelter": LAYERS / "dose_shelter.png",
    "dose_rate": LAYERS / "dose_rate.png",
}
WIDTH, HEIGHT = 1600, 1200


def set_texture(stage, path):
    shader = UsdShade.Shader(stage.GetPrimAtPath("/World/Looks/MarsGround/Ortho"))
    shader.GetInput("file").Set(Sdf.AssetPath(str(path)))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    omni.usd.get_context().open_stage(str(TERRAIN))
    for _ in range(10):
        simulation_app.update()
    stage = omni.usd.get_context().get_stage()

    # Plain light: the sky dome is switched off so the background has no depth
    for prim in stage.Traverse():
        if prim.IsA(UsdLux.DomeLight):
            prim.SetActive(False)
    sun = UsdLux.DistantLight.Define(stage, "/World/DrapeSun")
    sun.CreateIntensityAttr(2400.0)
    UsdGeom.Xformable(sun).AddRotateXYZOp().Set(Gf.Vec3f(45.0, 0.0, 30.0))
    UsdLux.DomeLight.Define(stage, "/World/DrapeAmbient").CreateIntensityAttr(900.0)

    # Oblique camera on the terrain, from the south-west, looking across the patch
    camera = UsdGeom.Camera.Define(stage, "/World/Cameras/Drape")
    camera.CreateFocalLengthAttr(16.0)
    camera.CreateClippingRangeAttr(Gf.Vec2f(5.0, 40000.0))
    eye, centre = Gf.Vec3d(-1250.0, -1380.0, 800.0), Gf.Vec3d(1036.0, 1036.0, 150.0)
    view = Gf.Matrix4d().SetLookAt(eye, centre, Gf.Vec3d(0, 0, 1))
    UsdGeom.Xformable(camera).AddTransformOp().Set(view.GetInverse())

    import omni.kit.viewport.utility as vp
    vp.get_active_viewport().camera_path = "/World/Cameras/Drape"
    for _ in range(20):
        simulation_app.update()

    product = rep.create.render_product("/World/Cameras/Drape", (WIDTH, HEIGHT))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    depth = rep.AnnotatorRegistry.get_annotator("distance_to_camera")
    rgb.attach([product])
    depth.attach([product])

    for name, texture in MAPS.items():
        set_texture(stage, texture)
        for _ in range(20):
            simulation_app.update()
        rep.orchestrator.step()
        colour = np.asarray(rgb.get_data())[..., :3]
        distance = np.asarray(depth.get_data()).reshape(colour.shape[:2])
        alpha = (np.isfinite(distance) & (distance > 0) & (distance < 1e6)).astype(np.uint8) * 255
        Image.fromarray(np.dstack([colour, alpha])).save(OUT / f"{name}.png")
        print(f"saved {name}.png, terrain covers {np.mean(alpha > 0):.0%} of the frame")

    simulation_app.close()


main()

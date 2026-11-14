"""Build the Mars terrain scene for Isaac Sim from the patch made by prepare_terrain.py.

Run with Isaac Sim's python.sh. Writes data/terrain/mars_gale.usd and, unless
--no-render is given, two test renders into media/screens/.

Scene frame: metres, Z up, origin in the south-west corner of the patch,
x east, y north (the same frame as data/terrain/meta.json).
"""

import argparse
import json
from pathlib import Path

import numpy as np

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--no-render", action="store_true", help="only write the USD file")
parser.add_argument("--headless", action="store_true", help="run without the Isaac Sim window")
args = parser.parse_args()

from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": args.headless, "width": 1280, "height": 720})

import omni.usd
from pxr import Gf, Sdf, UsdGeom, UsdLux, UsdPhysics, UsdShade, Vt

ROOT = Path(__file__).resolve().parents[1]
TERRAIN = ROOT / "data" / "terrain"
SCREENS = ROOT / "media" / "screens"
USD_PATH = TERRAIN / "mars_gale.usd"

EYE_HEIGHT = 1.7  # m, astronaut eye level above the ground
SKY_COLOR = (0.78, 0.55, 0.38)  # dusty Mars sky, an artistic choice


def terrain_arrays(heights, cell):
    """Vertices, quad indices, UVs and normals of the height grid."""
    ny, nx = heights.shape
    xs = np.arange(nx, dtype=np.float32) * cell
    ys = np.arange(ny, dtype=np.float32) * cell
    gx, gy = np.meshgrid(xs, ys)
    points = np.stack([gx, gy, heights], axis=-1).reshape(-1, 3)

    idx = np.arange(ny * nx, dtype=np.int32).reshape(ny, nx)
    quads = np.stack([idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]], axis=-1).reshape(-1)

    uvs = np.stack([gx / xs[-1], gy / ys[-1]], axis=-1).reshape(-1, 2).astype(np.float32)

    dz_dy, dz_dx = np.gradient(heights, cell)
    normals = np.stack([-dz_dx, -dz_dy, np.ones_like(heights)], axis=-1)
    normals /= np.linalg.norm(normals, axis=-1, keepdims=True)
    return points, quads, uvs, normals.reshape(-1, 3).astype(np.float32)


def add_terrain(stage, heights, cell):
    points, quads, uvs, normals = terrain_arrays(heights, cell)
    mesh = UsdGeom.Mesh.Define(stage, "/World/Terrain")
    mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(points))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(quads) // 4, 4, dtype=np.int32)))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(quads))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateNormalsAttr(Vt.Vec3fArray.FromNumpy(normals))
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    mesh.CreateExtentAttr([Gf.Vec3f(*points.min(axis=0).tolist()), Gf.Vec3f(*points.max(axis=0).tolist())])
    st = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
    st.Set(Vt.Vec2fArray.FromNumpy(uvs))

    material = UsdShade.Material.Define(stage, "/World/Looks/MarsGround")
    shader = UsdShade.Shader.Define(stage, "/World/Looks/MarsGround/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    reader = UsdShade.Shader.Define(stage, "/World/Looks/MarsGround/StReader")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    texture = UsdShade.Shader.Define(stage, "/World/Looks/MarsGround/Ortho")
    texture.CreateIdAttr("UsdUVTexture")
    # Prefer the 25 cm texture when prepare_terrain.py hires has made it
    image = "texture_hires.jpg" if (TERRAIN / "texture_hires.jpg").exists() else "texture.jpg"
    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(f"./{image}"))
    texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
    texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(
        reader.ConnectableAPI(), "result")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
        texture.ConnectableAPI(), "rgb")
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)

    # Static triangle-mesh collider with the friction of dry, firm ground
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
    UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim()).CreateApproximationAttr("none")
    ground = UsdShade.Material.Define(stage, "/World/Looks/GroundPhysics")
    friction = UsdPhysics.MaterialAPI.Apply(ground.GetPrim())
    friction.CreateStaticFrictionAttr(0.9)
    friction.CreateDynamicFrictionAttr(0.8)
    friction.CreateRestitutionAttr(0.0)
    UsdShade.MaterialBindingAPI(mesh.GetPrim()).Bind(
        ground, UsdShade.Tokens.weakerThanDescendants, "physics")


def add_lights(stage):
    sun = UsdLux.DistantLight.Define(stage, "/World/Sun")
    sun.CreateIntensityAttr(2500.0)
    sun.CreateAngleAttr(0.35)  # the Sun looks about two thirds as wide from Mars
    sun.CreateColorAttr(Gf.Vec3f(1.0, 0.93, 0.85))
    UsdGeom.Xformable(sun).AddRotateXYZOp().Set(Gf.Vec3f(55.0, 0.0, 40.0))

    sky = UsdLux.DomeLight.Define(stage, "/World/Sky")
    sky.CreateIntensityAttr(350.0)
    sky.CreateColorAttr(Gf.Vec3f(*SKY_COLOR))


def add_camera(stage, path, eye, target):
    camera = UsdGeom.Camera.Define(stage, path)
    camera.CreateFocalLengthAttr(18.0)
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.1, 20000.0))
    view = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1))
    UsdGeom.Xformable(camera).AddTransformOp().Set(view.GetInverse())
    return path


def ground_z(heights, cell, x, y):
    return float(heights[int(round(y / cell)), int(round(x / cell))])


def render(camera_paths):
    import omni.replicator.core as rep
    from PIL import Image

    SCREENS.mkdir(parents=True, exist_ok=True)
    for name, path in camera_paths.items():
        product = rep.create.render_product(path, (1280, 720))
        rgb = rep.AnnotatorRegistry.get_annotator("rgb")
        rgb.attach([product])
        for _ in range(60):  # let textures load and the image converge
            simulation_app.update()
        rep.orchestrator.step()
        Image.fromarray(rgb.get_data()[..., :3]).save(SCREENS / f"{name}.png")
        rgb.detach()
        product.destroy()
        print(f"saved {SCREENS / name}.png")


meta = json.loads((TERRAIN / "meta.json").read_text())
heights = np.load(TERRAIN / "heights.npy")
cell, size = meta["cell_m"], meta["size_m"]

omni.usd.get_context().new_stage()
stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.SetStageMetersPerUnit(stage, 1.0)
stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/World").GetPrim())

add_terrain(stage, heights, cell)
add_lights(stage)

# Astronaut view: standing in the middle of the patch, looking north-west
ax, ay = 0.55 * size, 0.40 * size
az = ground_z(heights, cell, ax, ay) + EYE_HEIGHT
cameras = {
    "astronaut_view": add_camera(stage, "/World/Cameras/Astronaut", (ax, ay, az), (ax - 300, ay + 300, az - 10)),
    "overview": add_camera(stage, "/World/Cameras/Overview",
                           (size * 1.05, -size * 0.35, meta["relief_m"] + 900),
                           (size * 0.5, size * 0.5, meta["relief_m"] * 0.4)),
}

stage.GetRootLayer().Export(str(USD_PATH))
print(f"saved {USD_PATH}")

# Reopen from disk, so the relative texture path resolves and we test the saved file
omni.usd.get_context().open_stage(str(USD_PATH))
for _ in range(10):
    simulation_app.update()

if not args.no_render:
    render(cameras)

# With the window open, keep the scene up until the user closes it
while not args.headless and simulation_app.is_running():
    simulation_app.update()

simulation_app.close()

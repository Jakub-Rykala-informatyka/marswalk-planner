"""Turn NASA's Z2 spacesuit model into USD for the simulation.

Source: NASA 3D Resources (free to use), https://github.com/nasa/NASA-3D-Resources,
"3D Models/Z2 Spacesuit". The model is static (no skeleton), so the astronaut
glides along the route.

  1. download data/raw/z2_spacesuit.glb (the URL below)
  2. python sim/decode_glb.py data/raw/z2_spacesuit.glb sim/assets/z2_spacesuit
     (any Python with numpy and DracoPy: the mesh is Draco-compressed)
  3. Isaac Sim's python.sh sim/prepare_astronaut.py

Writes sim/assets/z2_spacesuit/z2_spacesuit.usd (kept out of the repository).
"""

from pathlib import Path

import numpy as np
from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": False})  # pxr is only importable once the app runs

from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, Vt

ROOT = Path(__file__).resolve().parents[1]
URL = "https://raw.githubusercontent.com/nasa/NASA-3D-Resources/master/3D%20Models/Z2%20Spacesuit/Z2%20Spacesuit.glb"
ASSET = ROOT / "sim" / "assets" / "z2_spacesuit"
USD = ASSET / "z2_spacesuit.usd"

mesh_data = np.load(ASSET / "mesh.npz")
points, normals, uvs, faces = (mesh_data[k] for k in ("points", "normals", "uvs", "faces"))
# Stand the suit on the ground at the origin
points = points - [(points[:, 0].min() + points[:, 0].max()) / 2, (points[:, 1].min() + points[:, 1].max()) / 2,
                   points[:, 2].min()]

stage = Usd.Stage.CreateNew(str(USD))
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.SetStageMetersPerUnit(stage, 1.0)
root = UsdGeom.Xform.Define(stage, "/Z2")
stage.SetDefaultPrim(root.GetPrim())

mesh = UsdGeom.Mesh.Define(stage, "/Z2/Suit")
mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(points.astype(np.float32)))
mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(faces), 3, dtype=np.int32)))
mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(faces.reshape(-1)))
mesh.CreateNormalsAttr(Vt.Vec3fArray.FromNumpy(normals))
mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
mesh.CreateDoubleSidedAttr(True)
mesh.CreateExtentAttr([Gf.Vec3f(*points.min(0).tolist()), Gf.Vec3f(*points.max(0).tolist())])
UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex).Set(
    Vt.Vec2fArray.FromNumpy(uvs))

material = UsdShade.Material.Define(stage, "/Z2/Looks/Suit")
shader = UsdShade.Shader.Define(stage, "/Z2/Looks/Suit/Surface")
shader.CreateIdAttr("UsdPreviewSurface")
shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.5)
reader = UsdShade.Shader.Define(stage, "/Z2/Looks/Suit/StReader")
reader.CreateIdAttr("UsdPrimvarReader_float2")
reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
texture = UsdShade.Shader.Define(stage, "/Z2/Looks/Suit/Color")
texture.CreateIdAttr("UsdUVTexture")
texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("./color.jpg"))
texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(texture.ConnectableAPI(), "rgb")
material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)

stage.GetRootLayer().Save()
print(f"saved {USD}: {len(points)} points, height {points[:, 2].max():.2f} m")
simulation_app.close()

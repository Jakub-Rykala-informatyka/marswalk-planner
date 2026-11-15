"""A boulder for the Isaac Sim scenes: "Desert Rock Base" by bilgehan.korkmaz, CC BY 4.0.

Model: https://sketchfab.com/3d-models/desert-rock-base-62da7c177a6241eebe94c4eba6fc81b7
Author: https://sketchfab.com/bilgehan.korkmaz
License: Creative Commons Attribution 4.0, http://creativecommons.org/licenses/by/4.0/
Changes: scaled, turned and placed on the Gale terrain; nothing else.

Download the USDZ from that page into sim/assets/desert_rock/ (assets stay out of the
repository). Import inside a running SimulationApp: it needs pxr.
"""

from pathlib import Path

from pxr import Gf, Usd, UsdGeom

ROCK_USD = Path(__file__).resolve().parent / "assets" / "desert_rock" / "Desert_Rock_Base.usdz"
ROCK_CREDIT = '"Desert Rock Base" by bilgehan.korkmaz (Sketchfab), CC BY 4.0'


def add_rock(stage, path, x, y, ground_z, size_m=2.0, yaw_deg=0.0, sink_m=0.15):
    """Place the rock so it is size_m across, centred on (x, y), its base just under the ground.

    Returns (footprint radius, height above the ground) in metres, or None if the model
    is missing. The rock is visual only: no collider, so the rover never gets stuck on it.
    """
    if not ROCK_USD.exists():
        return None
    up_axis = UsdGeom.GetStageUpAxis(Usd.Stage.Open(str(ROCK_USD)))
    holder = UsdGeom.Xform.Define(stage, path)
    model = UsdGeom.Xform.Define(stage, f"{path}/Model")
    model.GetPrim().GetReferences().AddReference(str(ROCK_USD))
    if up_axis == UsdGeom.Tokens.y:
        UsdGeom.Xformable(model).AddRotateXOp().Set(90.0)  # Y-up export into the Z-up terrain

    bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"]).ComputeLocalBound(holder.GetPrim())
    box = bounds.ComputeAlignedRange()
    span = max(box.GetSize()[0], box.GetSize()[1])
    scale = size_m / span
    centre = box.GetMidpoint()
    ops = UsdGeom.Xformable(holder)
    ops.AddTranslateOp().Set(Gf.Vec3d(x, y, ground_z - sink_m))
    ops.AddRotateZOp().Set(yaw_deg)
    ops.AddScaleOp().Set(Gf.Vec3f(scale))
    # Centre the model over its own origin, base on z = 0, before the holder's scale and place
    UsdGeom.Xformable(model).AddTranslateOp(opSuffix="centre").Set(
        Gf.Vec3d(-centre[0], -centre[1], -box.GetMin()[2]))
    ops_order = UsdGeom.Xformable(model).GetOrderedXformOps()
    UsdGeom.Xformable(model).SetXformOpOrder([ops_order[-1], *ops_order[:-1]])
    return size_m / 2, box.GetSize()[2] * scale - sink_m

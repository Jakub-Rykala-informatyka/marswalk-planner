"""Assemble the crew rovers from Gosia's parts: chassis plus wheels, as STEP and GLB.

The single-file rovers in cad.rar (crew_pressurised, crew_open) do not match the
parts: their bodies are wider than the chassis and reach down into the wheels,
the wheels are a different width, and the mount markers have Inventor names
(Bryła2 …) instead of mount_<slot>_<n>. This script builds each rover again
from cad/parts/<rover>_chassis.step and <rover>_wheel.step (and the matching
GLBs in app/cad/):

- wheels on the ground, axles at wheel-radius height, a 5 cm gap from the chassis,
- mount markers renamed to mount_arm_1, mount_bay_1 … as in docs/cad_dla_gosi.md,
- GLB turned Z-up -> Y-up (glTF convention) and scaled to metres, so the
  dashboard shows it standing; mount markers become empty nodes at their place.

Writes cad/<rover>.step (one multi-body part, like the Inventor export) and
app/cad/<rover>.glb. Plain Python, no CAD kernel: the STEP wheels are copies of
the wheel's B-rep moved by a translation, which keeps every surface exact.
"""

import json
import re
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / "cad" / "parts"
GLB_DIR = ROOT / "app" / "cad"
GAP_M = 0.05  # between the chassis side and the wheel

ROVERS = {
    "crew_pressurised": {
        "axles_x": [2.0, 0.0, -2.0],  # m, front is +x
        "rows": ["front", "middle", "rear"],
        # Inventor body name (Bryła<n>) -> mount marker, by position in the chassis
        "mounts": {2: "mount_arm_1", 3: "mount_arm_2", 4: "mount_bay_1", 5: "mount_bay_2", 6: "mount_bay_3",
                   7: "mount_bay_4", 8: "mount_bay_5", 9: "mount_bay_6", 10: "mount_mast_1", 11: "mount_mast_2",
                   12: "mount_deck_1", 13: "mount_deck_2"},
    },
    "crew_open": {
        "axles_x": [1.1, -1.1],
        "rows": ["front", "rear"],
        "mounts": {2: "mount_arm_1", 3: "mount_bay_1", 4: "mount_bay_2", 5: "mount_bay_3", 6: "mount_bay_4",
                   7: "mount_mast_1", 8: "mount_deck_1", 9: "mount_deck_2"},
    },
}


# --- STEP --------------------------------------------------------------------

def read_step(path):
    text = path.read_text(encoding="latin-1")
    head, rest = text.split("DATA;", 1)
    data, tail = rest.rsplit("ENDSEC;", 1)
    entities = {int(m.group(1)): m.group(2).strip()
                for m in re.finditer(r"#(\d+)\s*=\s*(.*?);\s*(?=#\d+\s*=|\Z)", data, re.S)}
    return head, entities, "ENDSEC;" + tail


def refs(body):
    return [int(r) for r in re.findall(r"#(\d+)", body)]


def closure(entities, start):
    seen, todo = set(), list(start)
    while todo:
        n = todo.pop()
        if n in seen:
            continue
        seen.add(n)
        todo.extend(refs(entities[n]))
    return seen


def shift_points(body, dx, dy, dz):
    m = re.match(r"CARTESIAN_POINT\('([^']*)',\(([^)]*)\)\)", body)
    if not m:
        return body
    x, y, z = (float(v) for v in m.group(2).split(","))
    return f"CARTESIAN_POINT('{m.group(1)}',({x + dx!r},{y + dy!r},{z + dz!r}))"


def step_extent(entities, ids, axis):
    values = []
    for n in ids:
        m = re.match(r"CARTESIAN_POINT\('[^']*',\(([^)]*)\)\)", entities[n])
        if m:
            values.append(float(m.group(1).split(",")[axis]))
    return min(values), max(values)


def assemble_step(rover, spec, wheel_spots):
    head, chassis, tail = read_step(PARTS / f"{rover}_chassis.step")
    _, wheel, _ = read_step(PARTS / f"{rover}_wheel.step")

    # Rename the mount markers
    for n, body in chassis.items():
        m = re.match(r"MANIFOLD_SOLID_BREP\('Bry\\X2\\0142\\X0\\a(\d+)'", body)
        if m and int(m.group(1)) in spec["mounts"]:
            chassis[n] = body.replace(m.group(0), f"MANIFOLD_SOLID_BREP('{spec['mounts'][int(m.group(1))]}'")

    brep = next(n for n, b in wheel.items() if b.startswith("MANIFOLD_SOLID_BREP("))
    styled = [n for n, b in wheel.items() if b.startswith("STYLED_ITEM(") and f"#{brep})" in b.replace(" ", "")]
    copy_ids = closure(wheel, [brep, *styled])

    shape_rep = next(n for n, b in chassis.items() if b.startswith("ADVANCED_BREP_SHAPE_REPRESENTATION("))
    present_rep = next((n for n, b in chassis.items()
                        if b.startswith("MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION(")), None)
    next_id = max(chassis) + 1
    new_breps, new_styles = [], []
    for name, (x, y, z) in wheel_spots.items():
        offset = next_id - min(copy_ids)
        renum = lambda body: re.sub(r"#(\d+)", lambda r: f"#{int(r.group(1)) + offset}", body)
        for n in sorted(copy_ids):
            body = shift_points(renum(wheel[n]), x, y, z)
            if n == brep:
                body = re.sub(r"MANIFOLD_SOLID_BREP\('[^']*'", f"MANIFOLD_SOLID_BREP('{name}'", body)
            chassis[n + offset] = body
        new_breps.append(brep + offset)
        new_styles += [s + offset for s in styled]
        next_id = max(chassis) + 1

    def add_items(n, ids):
        # The first list of references in the entity is its items: (#14,#15,…)
        chassis[n] = re.sub(r"\((#[\d#,\s]*)\)", lambda m: "(" + m.group(1) + "".join(f",#{i}" for i in ids) + ")",
                            chassis[n], count=1)
    add_items(shape_rep, new_breps)
    if present_rep and new_styles:
        add_items(present_rep, new_styles)

    head = head.replace(f"'{rover}_chassis.step'", f"'{rover}.step'")
    for n, body in chassis.items():
        if body.startswith("PRODUCT("):
            chassis[n] = body.replace(f"'{rover}_chassis'", f"'{rover}'")
    data = "\n".join(f"#{n}={chassis[n]};" for n in sorted(chassis))
    out = ROOT / "cad" / f"{rover}.step"
    out.write_text(f"{head}DATA;\n{data}\n{tail}", encoding="latin-1")

    # Every reference must point at an entity that exists
    missing = {r for b in chassis.values() for r in refs(b)} - set(chassis)
    assert not missing, f"{rover}: dangling references {sorted(missing)[:5]}"
    return out


# --- GLB ---------------------------------------------------------------------

def read_glb(path):
    data = path.read_bytes()
    json_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_len])
    bin_start = 20 + json_len
    bin_len = struct.unpack("<I", data[bin_start:bin_start + 4])[0]
    return gltf, data[bin_start + 8:bin_start + 8 + bin_len]


def write_glb(path, gltf, blob):
    blob += b"\0" * (-len(blob) % 4)
    gltf["buffers"] = [{"byteLength": len(blob)}]
    text = json.dumps(gltf, separators=(",", ":")).encode()
    text += b" " * (-len(text) % 4)
    total = 12 + 8 + len(text) + 8 + len(blob)
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(text), 0x4E4F534A) + text
                     + struct.pack("<II", len(blob), 0x004E4942) + blob)


def accessor_centre(gltf, mesh_index):
    a = gltf["accessors"][gltf["meshes"][mesh_index]["primitives"][0]["attributes"]["POSITION"]]
    return [(lo + hi) / 2 for lo, hi in zip(a["min"], a["max"])]


def assemble_glb(rover, spec, wheel_spots_m):
    gltf, blob = read_glb(GLB_DIR / f"{rover}_chassis.glb")
    wheel, wheel_blob = read_glb(GLB_DIR / f"{rover}_wheel.glb")

    # Append the wheel's buffer, views, accessors, material and mesh
    blob += b"\0" * (-len(blob) % 4)
    base = len(blob)
    blob += wheel_blob
    view0, acc0, mat0, mesh0 = (len(gltf[k]) for k in ("bufferViews", "accessors", "materials", "meshes"))
    for view in wheel["bufferViews"]:
        gltf["bufferViews"].append(dict(view, buffer=0, byteOffset=view.get("byteOffset", 0) + base))
    for acc in wheel["accessors"]:
        gltf["accessors"].append(dict(acc, bufferView=acc["bufferView"] + view0))
    tyre = dict(wheel["materials"][0], name="tyre")
    tyre["pbrMetallicRoughness"] = {"baseColorFactor": [0.12, 0.12, 0.13, 1.0], "metallicFactor": 0.0, "roughnessFactor": 0.9}
    gltf["materials"].append(tyre)
    prim = wheel["meshes"][0]["primitives"][0]
    gltf["meshes"].append({"name": "wheel", "primitives": [{
        "attributes": {k: v + acc0 for k, v in prim["attributes"].items()},
        "indices": prim["indices"] + acc0, "material": mat0, "mode": prim.get("mode", 4)}]})

    # Part nodes in the parts' own centimetres; the root turns Z-up into Y-up and scales to metres
    nodes = [{"name": rover, "rotation": [-0.7071068, 0.0, 0.0, 0.7071068], "scale": [0.01, 0.01, 0.01], "children": []}]
    for node in gltf["nodes"]:
        m = re.match(r"Bry\S*?(\d+)$", node.get("name", ""))
        if m and int(m.group(1)) in spec["mounts"]:
            # A marker: an empty node where the part goes, not a little box at the origin
            nodes.append({"name": spec["mounts"][int(m.group(1))], "translation": accessor_centre(gltf, node["mesh"])})
        else:
            nodes.append({"name": node.get("name", "chassis"), "mesh": node["mesh"]})
    for name, (x, y, z) in wheel_spots_m.items():
        nodes.append({"name": name, "mesh": mesh0, "translation": [x * 100, y * 100, z * 100]})
    nodes[0]["children"] = list(range(1, len(nodes)))
    gltf["nodes"] = nodes
    gltf["scenes"] = [{"name": rover, "nodes": [0]}]
    gltf["scene"] = 0
    out = GLB_DIR / f"{rover}.glb"
    write_glb(out, gltf, bytes(blob))
    return out


def main():
    for rover, spec in ROVERS.items():
        _, chassis, _ = read_step(PARTS / f"{rover}_chassis.step")
        _, wheel, _ = read_step(PARTS / f"{rover}_wheel.step")
        main_body = next(n for n, b in chassis.items() if b.startswith("MANIFOLD_SOLID_BREP('chassis'"))
        half_width = step_extent(chassis, closure(chassis, [main_body]), 1)[1]
        wheel_ids = closure(wheel, [next(n for n, b in wheel.items() if b.startswith("MANIFOLD_SOLID_BREP("))])
        radius = -step_extent(wheel, wheel_ids, 0)[0]
        half_tyre = step_extent(wheel, wheel_ids, 1)[1]
        side = half_width + GAP_M + half_tyre
        spots = {}
        for row, x in zip(spec["rows"], spec["axles_x"]):
            spots[f"wheel_{row}_left"] = (x, side, radius)
            spots[f"wheel_{row}_right"] = (x, -side, radius)
        step = assemble_step(rover, spec, spots)
        glb = assemble_glb(rover, spec, spots)
        print(f"{rover}: chassis half width {half_width:.3f} m, wheel radius {radius:.3f} m, "
              f"wheels at y ±{side:.3f} m -> {step.relative_to(ROOT)}, {glb.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

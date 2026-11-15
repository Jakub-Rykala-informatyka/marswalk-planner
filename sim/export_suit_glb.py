"""Export the decoded Z2 spacesuit as a small GLB for the dashboard's 3D map.

Reads sim/assets/z2_spacesuit/mesh.npz and color.jpg (made by sim/decode_glb.py)
and writes app/models/astronaut.glb: Y-up as glTF expects, metres, feet at the
origin, facing +x (the walking direction at heading 0), texture cut to 1024 px.
Needs numpy and Pillow.
"""

import io
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "sim" / "assets" / "z2_spacesuit"
OUT = ROOT / "app" / "models" / "astronaut.glb"
TEXTURE_PX = 1024


def to_scene(v):
    """Suit frame (z up, facing -y) -> glTF (y up, facing +x)."""
    x, y, z = v[:, 0], v[:, 1], v[:, 2]
    x, y = -y, x  # turn 90 degrees about z: the suit now faces +x
    return np.stack([x, z, -y], axis=1).astype(np.float32)


def main():
    mesh = np.load(ASSET / "mesh.npz")
    points, normals = to_scene(mesh["points"]), to_scene(mesh["normals"])
    uvs = mesh["uvs"].copy()
    uvs[:, 1] = 1.0 - uvs[:, 1]  # decode_glb.py flipped v for USD; glTF images start at the top
    faces = mesh["faces"].astype(np.uint32)

    image = Image.open(ASSET / "color.jpg").convert("RGB")
    image.thumbnail((TEXTURE_PX, TEXTURE_PX))
    jpeg = io.BytesIO()
    image.save(jpeg, "JPEG", quality=85)

    chunks, views = b"", []
    for data, target in ((points.tobytes(), 34962), (normals.tobytes(), 34962), (uvs.astype(np.float32).tobytes(), 34962),
                         (faces.tobytes(), 34963), (jpeg.getvalue(), None)):
        chunks += b"\0" * (-len(chunks) % 4)
        view = {"buffer": 0, "byteOffset": len(chunks), "byteLength": len(data)}
        if target:
            view["target"] = target
        views.append(view)
        chunks += data
    chunks += b"\0" * (-len(chunks) % 4)

    gltf = {
        "asset": {"version": "2.0", "generator": "sim/export_suit_glb.py"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "astronaut", "mesh": 0}],
        "meshes": [{"name": "z2_spacesuit", "primitives": [{
            "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}, "indices": 3, "material": 0}]}],
        "materials": [{"name": "suit", "pbrMetallicRoughness": {
            "baseColorTexture": {"index": 0}, "metallicFactor": 0.0, "roughnessFactor": 0.8}}],
        "textures": [{"source": 0}],
        "images": [{"bufferView": 4, "mimeType": "image/jpeg"}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(points), "type": "VEC3",
             "min": points.min(0).tolist(), "max": points.max(0).tolist()},
            {"bufferView": 1, "componentType": 5126, "count": len(normals), "type": "VEC3"},
            {"bufferView": 2, "componentType": 5126, "count": len(uvs), "type": "VEC2"},
            {"bufferView": 3, "componentType": 5125, "count": faces.size, "type": "SCALAR"},
        ],
        "bufferViews": views,
        "buffers": [{"byteLength": len(chunks)}],
    }
    text = json.dumps(gltf, separators=(",", ":")).encode()
    text += b" " * (-len(text) % 4)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    total = 12 + 8 + len(text) + 8 + len(chunks)
    OUT.write_bytes(struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(text), 0x4E4F534A) + text
                    + struct.pack("<II", len(chunks), 0x004E4942) + chunks)
    print(f"saved {OUT.relative_to(ROOT)}: {len(faces)} triangles, height {points[:, 1].max():.2f} m, "
          f"{OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()

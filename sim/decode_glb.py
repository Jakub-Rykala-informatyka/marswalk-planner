"""Decode a single-mesh, Draco-compressed glTF (.glb) into arrays and a colour texture.

Step 1 of preparing the astronaut model; sim/prepare_astronaut.py turns the
output into USD. Needs numpy and DracoPy (pip install DracoPy), so it runs with
any Python that has them, not with Isaac Sim's.

  python decode_glb.py data/raw/z2_spacesuit.glb sim/assets/z2_spacesuit

Writes mesh.npz (points, normals, uvs, faces; metres, z up) and color.jpg.
"""

import json
import struct
import sys
from pathlib import Path

import DracoPy
import numpy as np


def quat_matrix(x, y, z, w):
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def main(glb_path, out_dir):
    data = Path(glb_path).read_bytes()
    json_length = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_length])
    binary = data[20 + json_length + 8:]

    def view(index):
        v = gltf["bufferViews"][index]
        start = v.get("byteOffset", 0)
        return binary[start:start + v["byteLength"]]

    node = gltf["nodes"][0]
    primitive = gltf["meshes"][node["mesh"]]["primitives"][0]
    draco = primitive["extensions"]["KHR_draco_mesh_compression"]
    mesh = DracoPy.decode(view(draco["bufferView"]))
    points = np.asarray(mesh.points, dtype=np.float64).reshape(-1, 3)
    normals = np.asarray(mesh.normals, dtype=np.float64).reshape(-1, 3)
    uvs = np.asarray(mesh.tex_coord, dtype=np.float32).reshape(-1, 2)
    faces = np.asarray(mesh.faces, dtype=np.int32).reshape(-1, 3)

    # Node rotation, then glTF y-up to the simulation's z-up
    rotation = quat_matrix(*node.get("rotation", [0, 0, 0, 1]))
    y_to_z = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])
    transform = y_to_z @ rotation
    points = points @ transform.T
    normals = normals @ transform.T
    uvs[:, 1] = 1.0 - uvs[:, 1]  # glTF images start at the top, USD textures at the bottom

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "mesh.npz", points=points.astype(np.float32), normals=normals.astype(np.float32),
                        uvs=uvs, faces=faces)

    # Base colour: the JPEG copy of the texture (the WebP one is an alternative)
    texture = gltf["materials"][primitive["material"]]["pbrMetallicRoughness"]["baseColorTexture"]["index"]
    image = gltf["images"][gltf["textures"][texture]["source"]]
    (out / "color.jpg").write_bytes(view(image["bufferView"]))
    print(f"{len(points)} points, {len(faces)} triangles, bounds {points.min(0).round(3)} .. {points.max(0).round(3)}")


if __name__ == "__main__":
    main(*sys.argv[1:3])

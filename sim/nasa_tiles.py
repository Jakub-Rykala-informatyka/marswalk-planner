"""Slide tiles that show the NASA data as NASA delivers it, before we compute anything.

- HiRISE orthoimage (RED band, 25 cm): grey, as in the PDS archive. Only the
  contrast stretch from prepare_terrain.py is applied; the Mars tint of the
  dashboard texture is left out.
- HiRISE terrain model (1 m posts): the elevation in metres, coloured from low
  (blue) to high (white) over a hillshade so the relief reads.

Both are draped on the same terrain mesh and seen from the same camera as the
Isaac Sim slide renders (sim/draped_maps.py --slide), here drawn with three.js
in headless Chrome so it can run while Isaac Sim is busy. Writes
media/slides/draped/nasa_ortho.png and nasa_dtm.png with a transparent
background, plus the elevation range for the label.
"""

import base64
import functools
import http.server
import json
import re
import subprocess
import tempfile
import threading
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TERRAIN = ROOT / "data" / "terrain"
OUT = ROOT / "media" / "slides" / "draped"
W, H = 1600, 1200
CROP_MARGIN = 24
# Low to high, the usual ramp for Mars elevation maps
RAMP = np.array([[38, 70, 160], [40, 150, 190], [70, 170, 90], [225, 210, 80], [205, 95, 45], [245, 240, 235]], float)

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<script type="importmap">{"imports":{"three":"https://unpkg.com/three@0.160.0/build/three.module.js"}}</script>
</head><body>
<script type="module">
import * as THREE from "three";
const meta = await (await fetch("grid.json")).json();
const z = new Float32Array(await (await fetch("heights.bin")).arrayBuffer());
const n = meta.n, cell = meta.cell;
const positions = new Float32Array(n * n * 3), uvs = new Float32Array(n * n * 2);
for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
  const k = i * n + j;  // row i runs south to north, column j west to east
  positions.set([j * cell, z[k], -i * cell], k * 3);  // local (x, y, z) -> three (x, z, -y)
  uvs.set([j / (n - 1), i / (n - 1)], k * 2);
}
const index = [];
for (let i = 0; i < n - 1; i++) for (let j = 0; j < n - 1; j++) {
  const a = i * n + j;
  index.push(a, a + 1, a + n, a + 1, a + n + 1, a + n);
}
const geometry = new THREE.BufferGeometry();
geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
geometry.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));
geometry.setIndex(index);
geometry.computeVertexNormals();

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(%(W)d, %(H)d);
renderer.setClearColor(0x000000, 0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
document.body.appendChild(renderer.domElement);

// The Isaac Sim slide camera: 16 mm lens, eye south-west of the patch, about 30 degrees down
const camera = new THREE.PerspectiveCamera(2 * Math.atan(20.955 * %(H)d / %(W)d / 2 / 16) * 180 / Math.PI, %(W)d / %(H)d, 5, 40000);
camera.position.set(-1250, 2100, 1380);
camera.lookAt(1036, 150, -1036);

const scene = new THREE.Scene();
scene.add(new THREE.AmbientLight(0xffffff, 1.4));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
sun.position.set(-600, 1000, 300);
scene.add(sun);
const mesh = new THREE.Mesh(geometry, new THREE.MeshLambertMaterial());
scene.add(mesh);

const loader = new THREE.TextureLoader();
for (const name of meta.textures) {
  const texture = await loader.loadAsync(name + ".png");
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  mesh.material.map = texture;
  mesh.material.needsUpdate = true;
  renderer.render(scene, camera);
  const out = document.createElement("pre");
  out.id = "out_" + name;
  out.textContent = renderer.domElement.toDataURL("image/png");
  document.body.appendChild(out);
}
</script></body></html>
"""


def main():
    meta = json.loads((TERRAIN / "meta.json").read_text())
    heights = np.load(TERRAIN / "heights.npy")
    work = Path(tempfile.mkdtemp(prefix="nasa_tiles_"))

    # Orthoimage: the red channel of the tinted texture is the stretched grey HiRISE band itself
    ortho = Image.open(TERRAIN / "texture_hires.jpg").getchannel("R")
    ortho.thumbnail((2048, 2048))
    ortho.convert("RGB").save(work / "nasa_ortho.png")

    # Terrain model: elevation in metres over a hillshade
    elevation = meta["elevation_of_z0_m"] + heights
    share = (heights - heights.min()) / np.ptp(heights)
    k = share * (len(RAMP) - 1)
    low = np.minimum(k.astype(int), len(RAMP) - 2)
    t = (k - low)[..., None]
    colour = RAMP[low] * (1 - t) + RAMP[low + 1] * t
    dy, dx = np.gradient(heights, meta["cell_m"])
    shade = np.clip(0.55 + 0.45 * (np.cos(np.arctan(np.hypot(dx, dy))) - 0.6 * dx / np.hypot(1, np.hypot(dx, dy))), 0, 1)
    Image.fromarray(np.flipud((colour * shade[..., None]).clip(0, 255).astype(np.uint8))).save(work / "nasa_dtm.png")

    step = 2
    z = heights[::step, ::step].astype(np.float32)
    (work / "heights.bin").write_bytes(z.tobytes())
    (work / "grid.json").write_text(json.dumps({"n": z.shape[0], "cell": meta["cell_m"] * step,
                                                "textures": ["nasa_ortho", "nasa_dtm"]}))
    (work / "index.html").write_text(PAGE % {"W": W, "H": H})

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(work))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        dom = subprocess.run(
            ["google-chrome", "--headless=new", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
             "--virtual-time-budget=60000", "--dump-dom", f"http://127.0.0.1:{server.server_port}/index.html"],
            capture_output=True, text=True, timeout=300).stdout
    finally:
        server.shutdown()

    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("nasa_ortho", "nasa_dtm"):
        m = re.search(rf'id="out_{name}">data:image/png;base64,([^<]+)<', dom)
        if not m:
            raise SystemExit(f"{name}: no image came back from Chrome")
        path = OUT / f"{name}.png"
        path.write_bytes(base64.b64decode(m.group(1)))
        image = Image.open(path)
        alpha = np.asarray(image.getchannel("A"))
        ys, xs = np.nonzero(alpha)
        box = (max(xs.min() - CROP_MARGIN, 0), max(ys.min() - CROP_MARGIN, 0),
               min(xs.max() + CROP_MARGIN + 1, W), min(ys.max() + CROP_MARGIN + 1, H))
        image.crop(box).save(path)
        print(f"saved {path.relative_to(ROOT)}, {image.crop(box).size[0]} x {image.crop(box).size[1]} px")
    print(f"elevation {elevation.min():.0f} .. {elevation.max():.0f} m")


if __name__ == "__main__":
    main()

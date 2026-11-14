// Dashboard: 3D terrain with NASA-derived layers and live data from ROS 2.
// Data uses the local frame of data/meta.json: metres, x east, y north, z up.
// Three.js is y up, so a point (x, y, z) is drawn at (x, z, -y).

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { initPlanner } from "./rover_planner.js";
import { loadToolNames, renderMission } from "./mission.js";

const MESH_STEP = 2; // use every 2nd height sample, about 4 m
const TRAIL_POINTS = 2000;
const LAYERS = [
  { id: "slope_classes", name: "Walkability (slope)", file: "/data/layers/slope_classes.png", opacity: 0.8, on: true, legend: "legend" },
  { id: "slope", name: "Slope", file: "/data/layers/slope.png", opacity: 0.6 },
  { id: "roughness", name: "Roughness", file: "/data/layers/roughness.png", opacity: 0.6 },
  { id: "dose_shelter", name: "Radiation shelter", file: "/data/layers/dose_shelter.png", opacity: 0.9, legend: "shelter-legend" },
  { id: "cost_walk", name: "Cost: walking", costmap: "walk", opacity: 0.7, legend: "cost-legend" },
  { id: "cost_rover", name: "Cost: crew rover", costmap: "rover", opacity: 0.7, legend: "cost-legend" },
];
const COLORS = { astronaut: 0x5fd4ff, rover: 0xffd23d, route: 0xffffff, goal: 0xff8a3d, crew: 0xeeeeee };

const $ = (id) => document.getElementById(id);
const fmt = (value, digits = 0) => value.toFixed(digits);
const toScene = (x, y, z) => new THREE.Vector3(x, z, -y);

// Read a float32 .npy grid; rows start at the south edge (see data/meta.json)
async function loadGrid(url) {
  const buffer = await (await fetch(url)).arrayBuffer();
  const headerLength = new DataView(buffer).getUint16(8, true);
  const header = new TextDecoder().decode(new Uint8Array(buffer, 10, headerLength));
  const [rows, cols] = header.match(/\((\d+),\s*(\d+)\)/).slice(1).map(Number);
  return { rows, cols, values: new Float32Array(buffer, 10 + headerLength) };
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = url;
  });
}

function routeProgress(route, x, y) {
  let gapBest = Infinity, walked = 0, total = 0;
  for (let i = 0; i < route.length; i++) {
    if (i) total += Math.hypot(route[i][0] - route[i - 1][0], route[i][1] - route[i - 1][1]);
    const gap = Math.hypot(route[i][0] - x, route[i][1] - y);
    if (gap < gapBest) { gapBest = gap; walked = total; }
  }
  return { walked, total };
}

async function main() {
  const meta = await (await fetch("/data/meta.json")).json();
  const terrain = await (await fetch("/data/terrain/meta.json")).json();
  const heights = await loadGrid("/data/terrain/heights.npy");
  const slopeGrid = await loadGrid("/data/layers/slope.npy");
  const size = meta.size_m, cell = meta.cell_m;

  const b = meta.bounds_deg;
  $("site-coords").textContent = `${fmt(-(b.north + b.south) / 2, 2)}°S ${fmt((b.west + b.east) / 2, 2)}°E`;
  $("sources").textContent = `(${terrain.source_dtm.replace(".IMG", "")})`;

  const sample = (grid, x, y) => {
    const ix = Math.round(x / cell), iy = Math.round(y / cell);
    if (ix < 0 || iy < 0 || ix >= grid.cols || iy >= grid.rows) return null;
    return grid.values[iy * grid.cols + ix];
  };
  const groundAt = (x, y) => {
    const fx = Math.min(Math.max(x / cell, 0), heights.cols - 1.001);
    const fy = Math.min(Math.max(y / cell, 0), heights.rows - 1.001);
    const ix = Math.floor(fx), iy = Math.floor(fy), tx = fx - ix, ty = fy - iy;
    const h = (i, j) => heights.values[j * heights.cols + i];
    return h(ix, iy) * (1 - tx) * (1 - ty) + h(ix + 1, iy) * tx * (1 - ty)
      + h(ix, iy + 1) * (1 - tx) * ty + h(ix + 1, iy + 1) * tx * ty;
  };

  // --- Scene --------------------------------------------------------------
  const view = $("view");
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  view.prepend(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xa38a72); // dusty Mars sky, an artistic choice
  scene.fog = new THREE.Fog(0xa38a72, 2500, 6000);
  const camera = new THREE.PerspectiveCamera(50, 1, 0.5, 20000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.48;
  controls.minDistance = 8;
  controls.maxDistance = 5000;

  scene.add(new THREE.HemisphereLight(0xffe6cc, 0x3a2a20, 1.1));
  const sun = new THREE.DirectionalLight(0xfff0dd, 2.2);
  sun.position.set(-800, 900, 600);
  scene.add(sun);

  // Terrain mesh from the HiRISE height grid
  const cols = Math.floor((heights.cols - 1) / MESH_STEP) + 1;
  const rows = Math.floor((heights.rows - 1) / MESH_STEP) + 1;
  const positions = new Float32Array(cols * rows * 3);
  const uvs = new Float32Array(cols * rows * 2);
  for (let j = 0; j < rows; j++) {
    for (let i = 0; i < cols; i++) {
      const k = j * cols + i, gx = i * MESH_STEP, gy = j * MESH_STEP;
      positions.set([gx * cell, heights.values[gy * heights.cols + gx], -gy * cell], 3 * k);
      uvs.set([gx / (heights.cols - 1), gy / (heights.rows - 1)], 2 * k);
    }
  }
  const indices = [];
  for (let j = 0; j < rows - 1; j++) {
    for (let i = 0; i < cols - 1; i++) {
      const a = j * cols + i, c = a + cols;
      indices.push(a, a + 1, c, a + 1, c + 1, c);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();

  // Texture: HiRISE image with the enabled layers painted on top
  const base = await loadImage("/data/terrain/texture.jpg");
  const canvas = Object.assign(document.createElement("canvas"), { width: base.width, height: base.height });
  const paint = canvas.getContext("2d");
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
  const terrainMesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ map: texture, roughness: 1, metalness: 0 }));
  scene.add(terrainMesh);

  const layerState = {};
  function repaint() {
    paint.globalAlpha = 1;
    paint.drawImage(base, 0, 0);
    for (const layer of LAYERS) {
      const state = layerState[layer.id];
      if (!state?.on || !state.image) continue;
      paint.globalAlpha = state.opacity;
      paint.drawImage(state.image, 0, 0, canvas.width, canvas.height);
    }
    texture.needsUpdate = true;
    for (const id of ["legend", "cost-legend", "shelter-legend"]) {
      $(id).hidden = !LAYERS.some((l) => l.legend === id && layerState[l.id]?.on);
    }
  }

  for (const layer of LAYERS) {
    const state = (layerState[layer.id] = { on: Boolean(layer.on), opacity: layer.opacity, image: null });
    if (layer.file) loadImage(layer.file).then((image) => { state.image = image; repaint(); });
    const label = document.createElement("label");
    label.innerHTML = `<input type="checkbox"><span>${layer.name}</span><input type="range" min="0" max="1" step="0.05" value="${layer.opacity}">`;
    const [toggle, slider] = label.querySelectorAll("input");
    toggle.checked = state.on;
    toggle.addEventListener("change", () => { state.on = toggle.checked; repaint(); });
    slider.addEventListener("input", () => { state.opacity = Number(slider.value); repaint(); });
    $("layers").append(label);
  }

  // Cost maps arrive from ROS 2 through the telemetry server, one byte per cell
  async function loadCostmap(variant) {
    const response = await fetch(`/costmap/${variant}`);
    if (!response.ok) return;
    const width = Number(response.headers.get("X-Width"));
    const height = Number(response.headers.get("X-Height"));
    const cells = new Int8Array(await response.arrayBuffer());
    const image = Object.assign(document.createElement("canvas"), { width, height });
    const context = image.getContext("2d");
    const pixels = context.createImageData(width, height);
    for (let row = 0; row < height; row++) {
      const source = row * width, target = (height - 1 - row) * width; // grid row 0 is south
      for (let col = 0; col < width; col++) {
        const cost = cells[source + col];
        const pixel = 4 * (target + col);
        if (cost >= 100) {
          pixels.data.set([200, 20, 60, 230], pixel);
        } else {
          // Low costs stay clear so the terrain shows through, then yellow to orange
          const t = cost / 99;
          pixels.data.set([255, 230 - 130 * t, 40, Math.round(200 * Math.sqrt(Math.max(0, (t - 0.15) / 0.85)))], pixel);
        }
      }
    }
    context.putImageData(pixels, 0, 0);
    layerState[`cost_${variant}`].image = image;
    repaint();
  }

  // --- Markers, route, trails and the lidar point cloud ---------------------
  const lift = (x, y, above) => toScene(x, y, groundAt(x, y) + above);

  const astronaut = new THREE.Mesh(new THREE.CapsuleGeometry(0.5, 1.0, 4, 12),
    new THREE.MeshStandardMaterial({ color: COLORS.astronaut, emissive: COLORS.astronaut, emissiveIntensity: 0.4 }));
  const astronautBeacon = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.15, 30, 6),
    new THREE.MeshBasicMaterial({ color: COLORS.astronaut, transparent: true, opacity: 0.5 }));
  const rover = new THREE.Mesh(new THREE.ConeGeometry(0.6, 1.6, 4),
    new THREE.MeshStandardMaterial({ color: COLORS.rover, emissive: COLORS.rover, emissiveIntensity: 0.3 }));
  rover.geometry.rotateZ(-Math.PI / 2); // cone points along +x, the heading 0
  // Goal: an arrow pointing down at the target, its tip on the ground
  const goalMarker = new THREE.Group();
  const goalArrow = new THREE.Group();
  const arrowMaterial = new THREE.MeshStandardMaterial({ color: COLORS.goal, emissive: COLORS.goal, emissiveIntensity: 0.5 });
  const arrowHead = new THREE.Mesh(new THREE.ConeGeometry(3, 6, 24), arrowMaterial);
  arrowHead.rotation.x = Math.PI; // tip down
  arrowHead.position.y = 3;
  const arrowShaft = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 10, 16), arrowMaterial);
  arrowShaft.position.y = 11;
  goalArrow.add(arrowHead, arrowShaft);
  goalMarker.add(goalArrow);
  const crewRover = new THREE.Mesh(new THREE.BoxGeometry(3.6, 2.2, 2),
    new THREE.MeshStandardMaterial({ color: COLORS.crew }));
  for (const marker of [astronaut, astronautBeacon, rover, goalMarker, crewRover]) { marker.visible = false; scene.add(marker); }

  const routeLine = new THREE.Line(new THREE.BufferGeometry(),
    new THREE.LineDashedMaterial({ color: COLORS.route, dashSize: 6, gapSize: 4, depthTest: false }));
  routeLine.renderOrder = 2;
  scene.add(routeLine);

  function makeTrail(color) {
    const line = new THREE.Line(new THREE.BufferGeometry(),
      new THREE.LineBasicMaterial({ color, depthTest: false, transparent: true, opacity: 0.85 }));
    line.geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(TRAIL_POINTS * 3), 3));
    line.geometry.setDrawRange(0, 0);
    line.renderOrder = 3;
    line.frustumCulled = false;
    line.userData = { count: 0, last: null };
    scene.add(line);
    return line;
  }
  const astronautTrail = makeTrail(COLORS.astronaut);
  const roverTrail = makeTrail(COLORS.rover);
  function pushTrail(trail, x, y) {
    const data = trail.userData;
    if (data.last && Math.hypot(data.last[0] - x, data.last[1] - y) < 0.5) return;
    data.last = [x, y];
    const attribute = trail.geometry.attributes.position;
    if (data.count === TRAIL_POINTS) { // drop the oldest point
      attribute.array.copyWithin(0, 3);
      data.count--;
    }
    attribute.array.set(lift(x, y, 0.3).toArray(), 3 * data.count++);
    attribute.needsUpdate = true;
    trail.geometry.setDrawRange(0, data.count);
  }
  function clearTrail(trail) {
    trail.userData.count = 0;
    trail.userData.last = null;
    trail.geometry.setDrawRange(0, 0);
  }

  // Lidar points come in the map frame (x, y, z as float32), coloured by height
  // above the HiRISE terrain: obstacles stand out from the ground
  const cloud = new THREE.Points(new THREE.BufferGeometry(),
    new THREE.PointsMaterial({ size: 0.25, vertexColors: true, sizeAttenuation: true }));
  cloud.frustumCulled = false;
  scene.add(cloud);
  $("show-points").addEventListener("change", () => { cloud.visible = $("show-points").checked; });
  async function loadPoints() {
    const response = await fetch("/points");
    if (!response.ok) return;
    const xyz = new Float32Array(await response.arrayBuffer());
    const count = xyz.length / 3;
    const scenePositions = new Float32Array(xyz.length);
    const colors = new Float32Array(xyz.length);
    const color = new THREE.Color();
    for (let i = 0; i < count; i++) {
      const x = xyz[3 * i], y = xyz[3 * i + 1], z = xyz[3 * i + 2];
      scenePositions.set([x, z, -y], 3 * i);
      const above = THREE.MathUtils.clamp((z - groundAt(x, y) + 0.5) / 2.5, 0, 1);
      color.setHSL(0.5 - 0.5 * above, 1, 0.55); // cyan on the ground to red on top of rocks
      colors.set([color.r, color.g, color.b], 3 * i);
    }
    cloud.geometry.dispose();
    cloud.geometry = new THREE.BufferGeometry();
    cloud.geometry.setAttribute("position", new THREE.BufferAttribute(scenePositions, 3));
    cloud.geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    $("rover-points").textContent = `${count.toLocaleString("en")}`;
  }

  let route = (await (await fetch("/data/route_example.geojson")).json()).features[0].geometry.coordinates;
  function drawRoute(points) {
    route = points;
    // Resample every 2 m so the line hugs the ground between route points
    const line = [];
    for (let i = 1; i < points.length; i++) {
      const [x0, y0] = points[i - 1], [x1, y1] = points[i];
      const n = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / 2));
      for (let k = 0; k < n; k++) line.push(lift(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n, 0.5));
    }
    const [gx, gy] = points[points.length - 1];
    line.push(lift(gx, gy, 0.5));
    routeLine.geometry.dispose();
    routeLine.geometry = new THREE.BufferGeometry().setFromPoints(line);
    routeLine.computeLineDistances();
    goalMarker.position.copy(lift(gx, gy, 0));
    goalMarker.visible = true;
  }
  drawRoute(route);

  // --- Camera ---------------------------------------------------------------
  const centre = toScene(size / 2, size / 2, groundAt(size / 2, size / 2));
  let followFrom = null;
  function overview() {
    controls.target.copy(centre);
    camera.position.copy(centre).add(new THREE.Vector3(size * 0.35, size * 0.55, size * 0.75));
    $("follow").checked = false;
    followFrom = null;
  }
  overview();
  $("follow").checked = true;
  $("overview").addEventListener("click", overview);

  function resize() {
    const { clientWidth: w, clientHeight: h } = view;
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(view);

  // Following: move the orbit target with the astronaut, keep the camera offset
  function follow(position) {
    if (!$("follow").checked) { followFrom = null; return; }
    if (!followFrom) { // first follow: swing in close behind
      controls.target.copy(position);
      camera.position.copy(position).add(new THREE.Vector3(35, 30, 35));
    } else {
      const shift = position.clone().sub(followFrom);
      controls.target.add(shift);
      camera.position.add(shift);
    }
    followFrom = position.clone();
  }

  // --- Picking: cursor readout and new goals --------------------------------
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  function pick(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObject(terrainMesh)[0];
    return hit ? { x: hit.point.x, y: -hit.point.z } : null;
  }

  let hoverEvent = null;
  renderer.domElement.addEventListener("pointermove", (event) => { hoverEvent = event; });
  renderer.domElement.addEventListener("pointerleave", () => { hoverEvent = null; $("readout").hidden = true; });

  let socket = null;
  let pressedAt = null;
  renderer.domElement.addEventListener("pointerdown", (event) => { pressedAt = [event.clientX, event.clientY]; });
  renderer.domElement.addEventListener("pointerup", (event) => {
    // A click, not the end of a drag to orbit the camera
    if (!pressedAt || Math.hypot(event.clientX - pressedAt[0], event.clientY - pressedAt[1]) > 5) return;
    const point = pick(event);
    if (!point || socket?.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ goal: point }));
    goalMarker.position.copy(lift(point.x, point.y, 0));
    $("plan-status").textContent = "Planning…";
  });

  function animate() {
    requestAnimationFrame(animate);
    if (hoverEvent) {
      const point = pick(hoverEvent);
      hoverEvent = null;
      const slope = point ? sample(slopeGrid, point.x, point.y) : null;
      $("readout").hidden = slope === null;
      if (slope !== null) $("readout").textContent = `x ${fmt(point.x)} m · y ${fmt(point.y)} m · slope ${fmt(slope, 1)}°`;
    }
    updatePins();
    goalArrow.position.y = 1.5 + 1.5 * Math.sin(performance.now() / 300); // bob above the target
    // Keep the arrow readable from far away: grow it with the camera distance
    goalMarker.scale.setScalar(Math.max(0.6, camera.position.distanceTo(goalMarker.position) / 250));
    controls.update();
    renderer.render(scene, camera);
  }

  // --- Tabs and camera feeds -------------------------------------------------
  let activeTab = "view";
  let plannerReady = false;
  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => {
      activeTab = tab.dataset.tab;
      if (activeTab === "planner" && !plannerReady) {
        plannerReady = true;
        initPlanner({
          send: (message) => {
            if (socket?.readyState !== WebSocket.OPEN) return false;
            socket.send(JSON.stringify(message));
            return true;
          },
        });
      }
      for (const other of document.querySelectorAll(".tab")) {
        const on = other === tab;
        other.classList.toggle("active", on);
        other.setAttribute("aria-selected", String(on));
        $(other.dataset.tab).hidden = !on;
      }
    });
  }

  const feeds = {};
  for (const name of ["astronaut", "rover", "arm"]) {
    const image = $(`camera-${name}`);
    feeds[name] = { version: null, loading: false, received: null };
    image.addEventListener("load", () => {
      feeds[name].loading = false;
      feeds[name].received = performance.now();
      $(`nosignal-${name}`).hidden = true;
    });
    image.addEventListener("error", () => { feeds[name].loading = false; });
  }
  function updateFeeds(versions) {
    for (const [name, feed] of Object.entries(feeds)) {
      const version = versions?.[name];
      // Fetch only while the tab is open and the previous frame has arrived
      if (activeTab === "cameras" && version && version !== feed.version && !feed.loading) {
        feed.version = version;
        feed.loading = true;
        $(`camera-${name}`).src = `/camera/${name}?v=${version}`;
      }
      const age = feed.received === null ? null : (performance.now() - feed.received) / 1000;
      $(`age-${name}`).textContent = age === null ? "waiting for ROS 2" : age < 2 ? "live" : `${fmt(age)} s old`;
    }
  }

  // --- Mission: numbered pins and the mission route on the 3D map ---------------
  await loadToolNames();
  const missionGroup = new THREE.Group();
  scene.add(missionGroup);
  const missionLine = new THREE.Line(new THREE.BufferGeometry(),
    new THREE.LineBasicMaterial({ color: 0x9ef0ff, depthTest: false, transparent: true, opacity: 0.9 }));
  missionLine.renderOrder = 2;
  scene.add(missionLine);
  function pin(label, color) {
    const label_canvas = Object.assign(document.createElement("canvas"), { width: 128, height: 128 });
    const c = label_canvas.getContext("2d");
    c.fillStyle = color; c.beginPath(); c.arc(64, 64, 56, 0, Math.PI * 2); c.fill();
    c.fillStyle = "#1a120d"; c.font = "bold 72px system-ui"; c.textAlign = "center"; c.textBaseline = "middle";
    c.fillText(label, 64, 68);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(label_canvas), depthTest: false }));
    sprite.renderOrder = 4;
    return sprite;
  }
  const pins = [];
  async function loadMission() {
    const plan = await (await fetch("/mission")).json();
    renderMission(plan);
    for (const old of [...missionGroup.children]) { missionGroup.remove(old); old.material.map.dispose(); old.material.dispose(); }
    pins.length = 0;
    if (!plan?.ok) return;
    const add = (label, color, x, y) => {
      const sprite = pin(label, color);
      sprite.userData.anchor = lift(x, y, 0);
      missionGroup.add(sprite);
      pins.push(sprite);
    };
    plan.targets.forEach((target, i) => add(String(i + 1), "#ff8a3d", target.x, target.y));
    add("R", "#eeeeee", plan.start.x, plan.start.y);
    const route = await (await fetch("/mission/route")).json();
    if (route.length > 1) {
      missionLine.geometry.dispose();
      missionLine.geometry = new THREE.BufferGeometry().setFromPoints(route.map(([x, y]) => lift(x, y, 0.8)));
    }
  }
  // Pins keep a readable size on screen and float above their target
  function updatePins() {
    for (const sprite of pins) {
      const distance = camera.position.distanceTo(sprite.userData.anchor);
      const size = Math.max(4, distance / 22);
      sprite.scale.setScalar(size);
      sprite.position.copy(sprite.userData.anchor).add(new THREE.Vector3(0, size * 0.9, 0));
    }
  }

  // Mission picker: switches the mission planner's mission over /mission/select
  fetch("/missions").then((r) => r.json()).then((list) => {
    for (const mission of list) {
      const option = new Option(mission.name, mission.file);
      option.selected = mission.file === "mission_boxwork.json";
      $("mission-select").append(option);
    }
  });
  $("mission-select").addEventListener("change", () => {
    if (socket?.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ mission_select: $("mission-select").value }));
    $("mission-sent").textContent = "Mission changed: planning…";
  });

  $("mission-start").addEventListener("click", () => {
    const ok = socket?.readyState === WebSocket.OPEN;
    if (ok) socket.send(JSON.stringify({ mission_start: true }));
    $("mission-sent").textContent = ok ? "Mission route sent to /route" : "Not connected to the server";
  });
  $("mission-show").addEventListener("click", () => {
    document.querySelector('.tab[data-tab="view"]').click();
    overview();
  });

  animate(); // after the mission pins exist, which every frame updates

  // --- Arm remote control ---------------------------------------------------
  const armConfig = await (await fetch("/data/arm_presets.json")).json();
  const armSliders = {};
  const deg = (rad) => (rad * 180) / Math.PI;
  let armPending = null;
  function sendArm(angles) {
    // Coalesce slider movement into at most ten commands a second
    armPending = { ...(armPending ?? {}), ...angles };
    if (sendArm.timer) return;
    sendArm.timer = setTimeout(() => {
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ arm_command: armPending }));
      armPending = null;
      sendArm.timer = null;
    }, 100);
  }
  for (const joint of armConfig.joints) {
    const row = document.createElement("label");
    row.className = "arm-joint";
    row.innerHTML = `<span>${joint.label}</span><input type="range" min="${joint.min}" max="${joint.max}" step="0.01" value="0"><output>–</output>`;
    const [slider, readout] = [row.querySelector("input"), row.querySelector("output")];
    slider.addEventListener("input", () => sendArm({ [joint.name]: Number(slider.value) }));
    armSliders[joint.name] = { slider, readout };
    $("arm-joints").append(row);
  }
  for (const [name, angles] of Object.entries(armConfig.presets)) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = name.replace("_", " ");
    button.addEventListener("click", () => {
      const command = Object.fromEntries(armConfig.joints.map((joint, i) => [joint.name, angles[i]]));
      for (const [joint, angle] of Object.entries(command)) armSliders[joint].slider.value = angle;
      sendArm(command);
    });
    $("arm-presets").append(button);
  }
  function showArm(arm) {
    if (!arm) return;
    for (const [name, { slider, readout }] of Object.entries(armSliders)) {
      if (arm[name] === undefined) continue;
      readout.textContent = `${fmt(deg(arm[name]), 1)}° / ${fmt(deg(Number(slider.value)), 0)}°`;
    }
  }

  // --- Telemetry ------------------------------------------------------------
  let missionVersion = null;
  const costVersions = {};
  let routeVersion = null;
  let pointsVersion = null;
  let pointsLoading = false;
  let lastTime = null;

  // Mission log: one row per change of phase, target or arm step, in simulation time
  let lastLogKey = null;
  function logProgress(progress, t) {
    const key = progress ? `${progress.phase}|${progress.target}|${progress.arm_step}` : null;
    if (!progress || progress.phase === "free walk" || key === lastLogKey) return;
    // A walk to the first target with nothing done yet = a new mission walk: start a new log
    if (progress.phase === "walking" && progress.done === 0) $("mission-log").replaceChildren();
    lastLogKey = key;
    const row = document.createElement("tr");
    const clock = t === null ? "–" : `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
    row.innerHTML = `<td>${clock}</td><td></td>`;
    row.lastChild.textContent = $("mission-live").firstChild?.textContent ?? progress.phase;
    $("mission-log").append(row);
    $("mission-log-box").hidden = false;
  }

  const ARM_STEPS = { forward: "reaching out", ground: "taking the sample", sample_box: "storing the sample", stow: "stowing" };
  function showProgress(progress) {
    const live = $("mission-live");
    if (!progress || progress.phase === "free walk") {
      live.hidden = true;
      $("hud-task").textContent = progress ? "Free walk" : "–";
      return;
    }
    let line, detail;
    if (progress.phase === "waiting for rover") {
      line = `${progress.number}. ${progress.target}: waiting for the rover arm`;
      detail = "Target too steep for the crew: the rover's arm takes the sample";
    } else if (progress.phase === "working") {
      const who = progress.executor.startsWith("arm") ? `Rover arm ${ARM_STEPS[progress.arm_step] ?? "working"}` : "Astronaut working";
      line = `${progress.number}. ${progress.target}: ${who}`;
      detail = `${progress.work_left_s} s left of ${progress.work_minutes} min of work (demo time is sped up)`;
    } else if (progress.phase === "walking") {
      line = `Walking to ${progress.number}. ${progress.target}`;
      detail = `${progress.distance_m} m to go · ${progress.done} of ${progress.stops} targets done`;
    } else {
      line = progress.phase === "done" ? "Mission complete" : "All targets done, returning to the crew rover";
      detail = `${progress.done} of ${progress.stops} targets done`;
    }
    live.innerHTML = `${line}<small>${detail}</small>`;
    live.hidden = false;
    $("hud-task").textContent = line;
  }

  function showPlan(summary) {
    if (!summary) return;
    if (!summary.ok) {
      $("plan-status").textContent = "No safe route to that point";
      return;
    }
    $("plan-status").textContent = "Route from the planner";
    $("plan-length").textContent = `${fmt(summary.length_m)} m`;
    $("plan-time").textContent = `${fmt(summary.walk_time_s / 60, 1)} min`;
    $("plan-dose").textContent = `${fmt(summary.dose_uSv, 1)} µSv`;
  }

  function showSuit(suit) {
    if (suit.dose_rate_uSv_h !== undefined) {
      const share = suit.dose_rate_uSv_h / meta.dose_model.open_ground_uSv_per_h;
      $("dose-rate").textContent = `${fmt(suit.dose_rate_uSv_h, 1)} µSv/h (${fmt(share * 100)} %)`;
      $("dose-total").textContent = `${fmt(suit.dose_uSv, 2)} µSv`;
    }
    if (suit.o2_pct === undefined) return;
    $("suit-o2").textContent = `${fmt(suit.o2_pct, 1)} % · ${fmt(suit.o2_left_min / 60, 1)} h`;
    $("o2-bar").style.width = `${suit.o2_pct}%`;
    $("o2-bar").classList.toggle("low", suit.turn_back);
    $("suit-battery").textContent = `${fmt(suit.battery_pct, 1)} %`;
    $("suit-return").textContent = `${fmt(suit.return_m)} m · ${fmt(suit.return_min, 1)} min`;
    $("suit-margin").textContent = `${fmt(suit.margin_min)} min`;
    $("suit-margin").className = suit.turn_back ? "bad" : "good";
    if (suit.support_rover) {
      $("suit-rover").textContent = suit.support_rover;
      $("suit-spare").textContent = suit.spare_o2_h
        ? `+${fmt(suit.spare_o2_h)} h ${suit.spare_in_field ? "in the field (counts in margin)" : "at the rover"}`
        : "none";
    }
    $("alert").hidden = !suit.turn_back;
    $("alert").textContent = "Turn back: oxygen margin for the return is almost used up";
    const [rx, ry] = suit.return_point;
    crewRover.position.copy(lift(rx, ry, 1.1));
    crewRover.visible = true;
  }

  function show(message) {
    if (message.mission && message.mission !== missionVersion) {
      missionVersion = message.mission;
      loadMission();
    }
    for (const [variant, version] of Object.entries(message.costmaps ?? {})) {
      if (costVersions[variant] !== version) {
        costVersions[variant] = version;
        loadCostmap(variant);
      }
    }
    if (message.route?.version && message.route.version !== routeVersion) {
      routeVersion = message.route.version;
      fetch("/route").then((r) => r.json()).then((points) => { if (points.length > 1) drawRoute(points); });
    }
    showPlan(message.route?.summary);
    if (message.points && message.points !== pointsVersion && !pointsLoading && cloud.visible) {
      pointsVersion = message.points;
      pointsLoading = true;
      loadPoints().finally(() => { pointsLoading = false; });
    }

    // Simulation time going backwards means a new walk: drop the old trails
    if (message.t !== null && lastTime !== null && message.t < lastTime - 1) {
      clearTrail(astronautTrail);
      clearTrail(roverTrail);
    }
    if (message.t !== null) lastTime = message.t;

    $("link").className = `pill ${message.live ? "online" : "offline"}`;
    $("link").textContent = message.live ? "Live from ROS 2" : "No telemetry";
    if (message.t !== null) {
      const seconds = Math.floor(message.t);
      $("clock").textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
    }

    const a = message.astronaut;
    if (a) {
      astronaut.position.copy(lift(a.x, a.y, 0.9));
      astronautBeacon.position.copy(lift(a.x, a.y, 15));
      astronaut.visible = astronautBeacon.visible = true;
      pushTrail(astronautTrail, a.x, a.y);
      follow(astronaut.position);
      $("astronaut-position").textContent = `${fmt(a.x)} m E, ${fmt(a.y)} m N`;
      $("astronaut-elevation").textContent = `${fmt(terrain.elevation_of_z0_m + a.z)} m`;
      $("astronaut-heading").textContent = `${fmt(((90 - a.heading_deg) % 360 + 360) % 360)}°`;
      const slope = sample(slopeGrid, a.x, a.y);
      $("astronaut-slope").textContent = slope === null ? "–" : `${fmt(slope, 1)}°`;
      const { walked, total } = routeProgress(route, a.x, a.y);
      $("progress").style.width = `${(100 * walked) / total}%`;
      $("progress-text").textContent = `${fmt(walked)} of ${fmt(total)} m`;
    }
    if (message.suit) showSuit(message.suit);
    showProgress(message.mission_progress);
    if (message.live) logProgress(message.mission_progress, message.t); // stale values from a stopped run stay out
    updateFeeds(message.cameras);
    showArm(message.arm);

    // Helmet-camera overlay: what the astronaut would see on the HUD
    if (a && route.length) {
      const [gx, gy] = route[route.length - 1];
      $("hud-target").textContent = `Target ${fmt(Math.hypot(gx - a.x, gy - a.y))} m`;
    }
    if (message.suit?.margin_min !== undefined) {
      $("hud-margin").textContent = `O₂ margin ${fmt(message.suit.margin_min)} min`;
      $("hud-margin").className = message.suit.turn_back ? "bad" : "";
    }
    if (message.rover_distance_m !== undefined) $("hud-rover").textContent = `Rover ${fmt(message.rover_distance_m, 1)} m`;

    const r = message.rover;
    if (r) {
      rover.position.copy(lift(r.x, r.y, 0.4));
      rover.rotation.y = (r.heading_deg * Math.PI) / 180;
      rover.visible = true;
      pushTrail(roverTrail, r.x, r.y);
      $("rover-state").textContent = r.state ?? "–";
      $("rover-distance").textContent = `${fmt(message.rover_distance_m, 1)} m`;
    }
  }

  function connect() {
    socket = new WebSocket(`ws://${location.host}/ws`);
    socket.onmessage = (event) => show(JSON.parse(event.data));
    socket.onclose = () => {
      $("link").className = "pill offline";
      $("link").textContent = "Server offline";
      setTimeout(connect, 1500);
    };
  }
  connect();
}

main();

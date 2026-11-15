// Rover planner tab: pick a rover, fit equipment, check the budgets, preview it in 3D.
// The catalogue lives in rover_catalog.json; all numbers there are concept values.
// Equipment shapes are simple stand-ins until the team's CAD models replace them.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const STORE_KEY = "marswalk.roverPlan";
const SLOT_NAMES = { arm: "Arm mounts", bay: "Cargo bays", mast: "Mast", deck: "Deck" };

const $ = (id) => document.getElementById(id);
const fmt = (value, digits = 0) => value.toFixed(digits);

function loadSaved() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY)) ?? null; } catch { return null; }
}
function save(plan) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(plan)); } catch { /* storage blocked: plan lives for this visit */ }
}

const cadScenes = {}; // id -> loaded scene, for the ids that have a model
const cadScale = {}; // id -> factor to metres: some exports store centimetres, some already metres

async function loadCad(ids) {
  const loader = new GLTFLoader();
  await Promise.all([...new Set(ids)].map((id) => new Promise((resolve) => {
    loader.load(`/app/cad/${id}.glb`, (gltf) => {
      const size = new THREE.Box3().setFromObject(gltf.scene).getSize(new THREE.Vector3());
      const largest = Math.max(size.x, size.y, size.z);
      cadScenes[id] = gltf.scene;
      cadScale[id] = largest > 20 ? 0.01 : 1; // a 20 m part can only be centimetres
      resolve();
    }, undefined, () => resolve());
  })));
}

export async function initPlanner({ send }) {
  const catalog = await (await fetch("/app/rover_catalog.json")).json();
  await loadCad([...catalog.rovers.map((r) => r.id), ...catalog.rovers.map((r) => `${r.id}_wheel`), ...catalog.equipment.map((e) => e.id)]);
  const rovers = Object.fromEntries(catalog.rovers.map((r) => [r.id, r]));
  const items = Object.fromEntries(catalog.equipment.map((e) => [e.id, e]));
  $("planner-note").textContent = catalog.note;

  const saved = loadSaved();
  let plan = saved && rovers[saved.rover] ? saved : { rover: "crew_pressurised", equipment: {} };

  // --- Budgets ------------------------------------------------------------
  function budget() {
    const rover = rovers[plan.rover];
    let mass = 0, power = 0, o2 = 0;
    const slots = Object.fromEntries(Object.keys(SLOT_NAMES).map((k) => [k, 0]));
    for (const [id, count] of Object.entries(plan.equipment)) {
      const item = items[id];
      if (!item || !count) continue;
      mass += item.mass_kg * count;
      power += item.power_w * count;
      o2 += (item.o2_hours ?? 0) * count;
      slots[item.slot] += count;
    }
    const draw = Math.max(rover.drive_w + power, 1);
    const hours = (rover.battery_kwh * 1000) / draw;
    const problems = [];
    if (mass > rover.payload_kg) problems.push(`payload over by ${fmt(mass - rover.payload_kg)} kg`);
    for (const [slot, used] of Object.entries(slots)) {
      if (used > rover.slots[slot]) problems.push(`${SLOT_NAMES[slot].toLowerCase()}: ${used} of ${rover.slots[slot]}`);
    }
    return { rover, mass, power, o2, slots, hours, range: hours * rover.speed_kmh, problems };
  }

  // --- Rover cards and equipment list ----------------------------------------
  function renderRovers() {
    $("planner-rovers").replaceChildren(...catalog.rovers.map((rover) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = `rover-card${rover.id === plan.rover ? " selected" : ""}`;
      card.innerHTML = `<b>${rover.name}</b><span>${rover.summary}</span>
        <small>${rover.crew ? `${rover.crew} crew · ` : ""}payload ${rover.payload_kg} kg · up to ${rover.max_slope_deg}° · ${rover.speed_kmh} km/h</small>`;
      card.addEventListener("click", () => {
        const previous = plan.equipment;
        plan = { rover: rover.id, equipment: {} };
        // Keep what still fits the new rover
        for (const [id, count] of Object.entries(previous)) {
          if (items[id]?.sizes.includes(rover.size)) plan.equipment[id] = Math.min(count, items[id].max);
        }
        update();
      });
      return card;
    }));
  }

  function renderEquipment() {
    const rover = rovers[plan.rover];
    const groups = {};
    for (const item of catalog.equipment) (groups[item.group] ??= []).push(item);
    $("planner-equipment").replaceChildren(...Object.entries(groups).map(([group, list]) => {
      const section = document.createElement("div");
      section.className = "equip-group";
      section.innerHTML = `<h3>${group}</h3>`;
      for (const item of list) {
        const fits = item.sizes.includes(rover.size);
        const count = plan.equipment[item.id] ?? 0;
        const row = document.createElement("div");
        row.className = `equip-row${fits ? "" : " unfit"}`;
        row.title = item.use;
        row.innerHTML = `
          <div><b>${item.name}</b><span>${fits ? item.use : `Does not fit a ${rover.size} rover`}</span>
            <small>${item.mass_kg} kg · ${item.power_w > 0 ? `${item.power_w} W` : item.power_w < 0 ? `+${-item.power_w} W` : "no power"} · ${SLOT_NAMES[item.slot].toLowerCase()}</small></div>
          <div class="stepper">
            <button type="button" aria-label="Remove one ${item.name}" ${!fits || !count ? "disabled" : ""}>−</button>
            <output>${count}</output>
            <button type="button" aria-label="Add one ${item.name}" ${!fits || count >= item.max ? "disabled" : ""}>+</button>
          </div>`;
        const [minus, plus] = row.querySelectorAll("button");
        minus.addEventListener("click", () => { plan.equipment[item.id] = count - 1; update(); });
        plus.addEventListener("click", () => { plan.equipment[item.id] = count + 1; update(); });
        section.append(row);
      }
      return section;
    }));
  }

  function bar(label, used, total, unit, digits = 0) {
    const share = total > 0 ? used / total : used > 0 ? 2 : 0;
    return `<div class="budget-row"><p class="row"><span>${label}</span><b class="${share > 1 ? "bad" : ""}">${fmt(used, digits)} / ${fmt(total, digits)} ${unit}</b></p>
      <div class="bar"><div style="width:${Math.min(100, share * 100)}%;background:${share > 1 ? "var(--bad)" : share > 0.85 ? "var(--rover)" : "var(--ok)"}"></div></div></div>`;
  }

  function renderBudget() {
    const b = budget();
    const slotBars = Object.keys(SLOT_NAMES).filter((k) => b.rover.slots[k] > 0 || b.slots[k] > 0)
      .map((k) => bar(SLOT_NAMES[k], b.slots[k], b.rover.slots[k], ""));
    $("planner-budget").innerHTML = `
      ${bar("Payload", b.mass, b.rover.payload_kg, "kg")}
      ${slotBars.join("")}
      <p class="row"><span>Equipment power</span><b>${b.power >= 0 ? fmt(b.power) : `+${fmt(-b.power)}`} W</b></p>
      <p class="row"><span>Driving on one charge</span><b>${fmt(b.hours, 1)} h · ${fmt(b.range)} km</b></p>
      <p class="row"><span>Extra suit oxygen</span><b>${b.o2 ? `+${fmt(b.o2)} h` : "none"}</b></p>
      <p class="row"><span>Max slope / shelter</span><b>${b.rover.max_slope_deg}° / ${b.rover.shelter ? "yes" : "no"}</b></p>
      <p class="planner-status ${b.problems.length ? "bad" : "good"}">${b.problems.length ? `Not valid: ${b.problems.join(", ")}` : "Configuration fits"}</p>`;
    $("planner-send").disabled = b.problems.length > 0;
    return b;
  }

  // --- 3D preview -------------------------------------------------------------
  const view = $("planner-view");
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  view.prepend(renderer.domElement);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x2a211c);
  const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 200);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.49;
  scene.add(new THREE.HemisphereLight(0xffe6cc, 0x3a2a20, 1.2));
  const sun = new THREE.DirectionalLight(0xfff0dd, 2.0);
  sun.position.set(5, 8, 4);
  scene.add(sun);
  const ground = new THREE.Mesh(new THREE.CircleGeometry(30, 48),
    new THREE.MeshStandardMaterial({ color: 0x8a5a3c, roughness: 1 }));
  ground.rotation.x = -Math.PI / 2;
  scene.add(ground);
  let model = null;

  const material = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.7, metalness: 0.1, ...extra });
  const box = (w, h, d, color) => new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material(color));
  const cylinder = (r, h, color, segments = 16) => new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, segments), material(color));

  // Equipment stand-ins, built in a unit size and scaled with the rover
  function equipmentShape(id) {
    const group = new THREE.Group();
    switch (id) {
      case "arm_heavy":
      case "arm_light": {
        const thick = id === "arm_heavy" ? 0.09 : 0.05;
        const base = cylinder(thick * 1.6, 0.12, 0x555555);
        const upper = cylinder(thick, 0.7, 0xdddddd);
        upper.position.set(0, 0.4, 0);
        const lower = cylinder(thick * 0.8, 0.6, 0xdddddd);
        lower.rotation.z = -1.1;
        lower.position.set(0.27, 0.85, 0);
        const grip = box(thick * 2.4, 0.12, thick * 2.4, 0xff8a3d);
        grip.position.set(0.55, 0.98, 0);
        group.add(base, upper, lower, grip);
        break;
      }
      case "core_drill": {
        const tower = box(0.18, 0.7, 0.18, 0x8c8c8c);
        tower.position.y = 0.35;
        const bit = cylinder(0.03, 0.4, 0x333333, 8);
        bit.position.y = -0.1;
        group.add(tower, bit);
        break;
      }
      case "o2_tank": {
        const tank = cylinder(0.11, 0.55, 0xf4f1ea);
        tank.rotation.z = Math.PI / 2;
        tank.position.y = 0.11;
        const band = cylinder(0.115, 0.06, 0x2f8f5b);
        band.rotation.z = Math.PI / 2;
        band.position.y = 0.11;
        group.add(tank, band);
        break;
      }
      case "lidar": { const head = cylinder(0.08, 0.1, 0x222222); head.position.y = 0.05; group.add(head); break; }
      case "pan_cam": { const head = box(0.25, 0.1, 0.1, 0x333333); head.position.y = 0.05; group.add(head); break; }
      case "comm_relay": {
        const dish = new THREE.Mesh(new THREE.ConeGeometry(0.3, 0.12, 24, 1, true), material(0xeeeeee, { side: THREE.DoubleSide }));
        dish.rotation.x = Math.PI;
        dish.position.y = 0.1;
        group.add(dish);
        break;
      }
      case "solar_panel": {
        const panel = box(1.0, 0.03, 0.7, 0x1d3a6e);
        panel.position.y = 0.05;
        group.add(panel);
        break;
      }
      case "gpr": { const unit = box(0.6, 0.08, 0.35, 0x444c55); unit.position.y = 0.04; group.add(unit); break; }
      case "winch": { const drum = cylinder(0.1, 0.3, 0x555555); drum.rotation.z = Math.PI / 2; drum.position.y = 0.1; group.add(drum); break; }
      default: { // crates and kits
        const colors = { geo_tools: 0xff8a3d, sample_box: 0xc9c2b6, suit_battery: 0x2b2b2b, repair_kit: 0xd23c3c, spectrometer: 0x5fd4ff };
        const crate = box(0.3, 0.2, 0.25, colors[id] ?? 0x999999);
        crate.position.y = 0.1;
        group.add(crate);
      }
    }
    return group;
  }

  function buildModel() {
    if (model) {
      scene.remove(model);
      model.traverse((o) => { o.geometry?.dispose(); o.material?.dispose?.(); });
    }
    const rover = rovers[plan.rover];
    const { length: L, width: W, height: H, wheels, wheel_radius: R, cabin, color } = rover.body;
    const scale = L / 3.6; // equipment stand-ins are sized for a 3.6 m rover
    model = new THREE.Group();

    const deckY = R * 1.3 + H / 2;
    let top = deckY + H / 2;
    const bodyModel = cadScenes[plan.rover];
    if (bodyModel) {
      // CAD body: standing on the ground at the origin, centred over the wheels
      const body = bodyModel.clone(true);
      body.scale.setScalar(cadScale[plan.rover]);
      const bounds = new THREE.Box3().setFromObject(body);
      const centre = bounds.getCenter(new THREE.Vector3());
      let hasWheels = false;
      body.traverse((node) => { if (/wheel/i.test(node.name)) hasWheels = true; });
      // An assembled rover (cad/assemble_rovers.py) stands on its own wheels; a bare body rests on added ones
      const lift = hasWheels ? 0 : R * 1.3;
      body.position.set(-centre.x, lift - bounds.min.y, -centre.z);
      model.add(body);
      top = lift + (bounds.max.y - bounds.min.y);
      // Wheels: Gosia exports some bodies without them, so the wheel part is placed at the catalogue spots
      const wheelModel = cadScenes[`${plan.rover}_wheel`];
      if (wheelModel && !hasWheels) {
        const xs = wheels > 4 ? [-0.38 * L, 0, 0.38 * L] : [-0.36 * L, 0.36 * L];
        for (const x of xs) {
          for (const side of [-1, 1]) {
            const wheel = wheelModel.clone(true);
            wheel.scale.setScalar(cadScale[`${plan.rover}_wheel`]);
            wheel.rotation.x = Math.PI / 2; // the export lies flat: its thin axis is Y, the wheel's axle is Z
            wheel.updateMatrixWorld(true);
            const wb = new THREE.Box3().setFromObject(wheel);
            const wc = wb.getCenter(new THREE.Vector3());
            wheel.position.set(x - wc.x, R - wc.y, side * (W / 2 + 0.15) - wc.z);
            model.add(wheel);
          }
        }
      }
    } else {
      const chassis = box(L, H, W, color);
      chassis.position.y = deckY;
      model.add(chassis);
    }

    const perSide = bodyModel ? 0 : wheels / 2;
    for (let i = 0; i < perSide; i++) {
      const x = perSide === 1 ? 0 : -L * 0.38 + (i * L * 0.76) / (perSide - 1);
      for (const side of [-1, 1]) {
        const wheel = cylinder(R, R * 0.6, 0x2a2a2a, 24);
        wheel.rotation.x = Math.PI / 2;
        wheel.position.set(x, R, side * (W / 2 + R * 0.35));
        const hub = cylinder(R * 0.45, R * 0.62, 0xb08a3a, 12);
        hub.rotation.x = Math.PI / 2;
        hub.position.copy(wheel.position);
        model.add(wheel, hub);
      }
    }

    if (cabin && !bodyModel) {
      const shell = new THREE.Mesh(new THREE.CapsuleGeometry(W * 0.42, L * 0.32, 8, 24), material(0xf4f1ea));
      shell.rotation.z = Math.PI / 2;
      shell.position.set(L * 0.12, top + W * 0.38, 0);
      // Front window: a dark, flattened dome on the nose of the cabin
      const nose = L * 0.12 + L * 0.16 + W * 0.42;
      const window = new THREE.Mesh(new THREE.SphereGeometry(W * 0.3, 24, 16), material(0x1a2230, { metalness: 0.6, roughness: 0.2 }));
      window.scale.set(0.35, 0.6, 1);
      window.position.set(nose - W * 0.12, top + W * 0.45, 0);
      model.add(shell, window);
    }

    // Mount points per slot type, filled in order. With a cabin the cargo
    // goes on the rear deck behind it and deck items on its roof.
    const bayRows = cabin ? [-0.3, -0.38, -0.46] : [0.1, -0.05, -0.2, -0.35];
    const roof = top + W * 0.84;
    const slotSpots = {
      arm: [[L * 0.42, top, W * 0.3], [L * 0.42, top, -W * 0.3]],
      bay: bayRows.flatMap((x) => [-0.3, 0, 0.3].map((z) => [L * x, top, W * z])),
      mast: [[-L * 0.46, top, W * 0.45]],
      deck: cabin ? [[L * 0.02, roof, 0], [L * 0.24, roof, 0]] : [[-L * 0.42, top + 0.02, -W * 0.15], [L * 0.25, top + 0.02, 0]],
    };
    // Gosia's bodies carry empty nodes named mount_<slot>_<n> where each part goes
    if (bodyModel) {
      model.updateMatrixWorld(true);
      const found = { arm: [], bay: [], mast: [], deck: [] };
      model.traverse((node) => {
        const m = /^mount_(arm|bay|mast|deck)_(\d+)$/.exec(node.name);
        if (m) found[m[1]].push({ n: Number(m[2]), at: node.getWorldPosition(new THREE.Vector3()) });
      });
      for (const slot of Object.keys(found)) {
        if (found[slot].length) {
          found[slot].sort((a, b) => a.n - b.n);
          slotSpots[slot] = found[slot].map(({ at }) => [at.x, at.y, at.z]);
        }
      }
    }
    const used = { arm: 0, bay: 0, mast: 0, deck: 0 };
    let mastHeight = 0;
    for (const [id, count] of Object.entries(plan.equipment)) {
      const item = items[id];
      for (let k = 0; k < count; k++) {
        const cad = cadScenes[id];
        const shape = cad ? cad.clone(true) : equipmentShape(id);
        if (cad) shape.scale.setScalar(cadScale[id]); else shape.scale.setScalar(scale);
        // A CAD part stands with its bottom on the mount point; stand-ins keep their origin there
        const seat = (x, y, z) => {
          if (!cad) { shape.position.set(x, y, z); return; }
          const low = new THREE.Box3().setFromObject(shape).min.y;
          shape.position.set(x, y - low, z);
        };
        if (item.slot === "mast") {
          if (!mastHeight) { // the pole itself, once
            const pole = cylinder(0.04 * scale, 1.0 * scale, 0xdddddd);
            pole.position.set(slotSpots.mast[0][0], top + 0.5 * scale, slotSpots.mast[0][2]);
            model.add(pole);
          }
          mastHeight += 1;
          seat(slotSpots.mast[0][0], top + (0.75 + 0.18 * mastHeight) * scale, slotSpots.mast[0][2]);
        } else {
          const spots = slotSpots[item.slot];
          const spot = spots[used[item.slot] % spots.length];
          // Extra items of a full slot type stack upwards
          const layer = Math.floor(used[item.slot] / spots.length);
          seat(spot[0], spot[1] + layer * 0.22 * scale, spot[2]);
          used[item.slot] += 1;
        }
        model.add(shape);
      }
    }
    scene.add(model);

    const span = Math.max(L, W) * 1.1 + 0.6;
    controls.target.set(0, deckY, 0);
    camera.position.set(span * 1.1, span * 0.8, span * 1.3);
    controls.minDistance = span * 0.4;
    controls.maxDistance = span * 6;
  }

  function resize() {
    const { clientWidth: w, clientHeight: h } = view;
    if (!w || !h) return;
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(view);
  (function animate() {
    requestAnimationFrame(animate);
    if (!view.offsetParent) return; // tab hidden
    controls.update();
    renderer.render(scene, camera);
  })();

  // --- Output -------------------------------------------------------------------
  function planJson() {
    const b = budget();
    return {
      rover: plan.rover,
      rover_name: b.rover.name,
      equipment: Object.fromEntries(Object.entries(plan.equipment).filter(([, n]) => n > 0)),
      payload_kg: b.mass,
      equipment_power_w: b.power,
      drive_hours: Number(b.hours.toFixed(2)),
      range_km: Number(b.range.toFixed(1)),
      extra_o2_hours: b.o2,
      max_slope_deg: b.rover.max_slope_deg,
      shelter: b.rover.shelter,
    };
  }
  $("planner-send").addEventListener("click", () => {
    const sent = send({ rover_config: planJson() });
    $("planner-sent").textContent = sent ? "Sent to ROS 2 on /rover/config" : "Not connected to the server";
  });
  $("planner-download").addEventListener("click", () => {
    const link = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(new Blob([JSON.stringify(planJson(), null, 2)], { type: "application/json" })),
      download: `rover_${plan.rover}.json`,
    });
    link.click();
    URL.revokeObjectURL(link.href);
  });

  function update() {
    save(plan);
    $("planner-sent").textContent = "";
    renderRovers();
    renderEquipment();
    renderBudget();
    buildModel();
  }
  update();
}

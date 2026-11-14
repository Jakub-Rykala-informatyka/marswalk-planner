// Dashboard: terrain map with NASA-derived layers and live poses from ROS 2.
// Map coordinates are the local frame of data/meta.json: metres, x east, y north.

const TRAIL_POINTS = 600;
const LAYERS = [
  { id: "slope_classes", name: "Walkability (slope)", file: "/data/layers/slope_classes.png", opacity: 0.8, on: true, legend: true },
  { id: "slope", name: "Slope", file: "/data/layers/slope.png", opacity: 0.6 },
  { id: "roughness", name: "Roughness", file: "/data/layers/roughness.png", opacity: 0.6 },
  { id: "sky_view", name: "Open sky", file: "/data/layers/sky_view.png", opacity: 0.6 },
];

const $ = (id) => document.getElementById(id);
const fmt = (value, digits = 0) => value.toFixed(digits);

// Read a float32 .npy grid; rows start at the south edge (see data/meta.json)
async function loadGrid(url) {
  const buffer = await (await fetch(url)).arrayBuffer();
  const headerLength = new DataView(buffer).getUint16(8, true);
  const header = new TextDecoder().decode(new Uint8Array(buffer, 10, headerLength));
  const [rows, cols] = header.match(/\((\d+),\s*(\d+)\)/).slice(1).map(Number);
  return { rows, cols, values: new Float32Array(buffer, 10 + headerLength) };
}

function sample(grid, cell, x, y) {
  const ix = Math.round(x / cell), iy = Math.round(y / cell);
  if (!grid || ix < 0 || iy < 0 || ix >= grid.cols || iy >= grid.rows) return null;
  return grid.values[iy * grid.cols + ix];
}

function routeProgress(route, x, y) {
  let best = 0, bestGap = Infinity, walked = 0, total = 0;
  for (let i = 0; i < route.length; i++) {
    if (i) total += Math.hypot(route[i][0] - route[i - 1][0], route[i][1] - route[i - 1][1]);
    const gap = Math.hypot(route[i][0] - x, route[i][1] - y);
    if (gap < bestGap) { bestGap = gap; best = i; walked = total; }
  }
  return { walked, total };
}

async function main() {
  const meta = await (await fetch("/data/meta.json")).json();
  const terrain = await (await fetch("/data/terrain/meta.json")).json();
  const size = meta.size_m, cell = meta.cell_m;
  const bounds = [[0, 0], [size, size]];

  const b = meta.bounds_deg;
  $("site-coords").textContent =
    `${fmt(-(b.north + b.south) / 2, 2)}°S ${fmt((b.west + b.east) / 2, 2)}°E`;
  $("sources").textContent = `(${terrain.source_dtm.replace(".IMG", "")})`;

  const map = L.map("map", { crs: L.CRS.Simple, minZoom: -2, maxZoom: 4, zoomSnap: 0.25, attributionControl: false });
  L.imageOverlay("/data/terrain/texture.jpg", bounds).addTo(map);
  map.fitBounds(bounds);

  for (const layer of LAYERS) {
    const overlay = L.imageOverlay(layer.file, bounds, { opacity: layer.opacity });
    const label = document.createElement("label");
    label.innerHTML = `<input type="checkbox"><span>${layer.name}</span><input type="range" min="0" max="1" step="0.05" value="${layer.opacity}">`;
    const [toggle, slider] = label.querySelectorAll("input");
    toggle.checked = Boolean(layer.on);
    const refresh = () => {
      toggle.checked ? overlay.addTo(map) : overlay.remove();
      if (layer.legend) $("legend").hidden = !toggle.checked;
    };
    toggle.addEventListener("change", refresh);
    slider.addEventListener("input", () => overlay.setOpacity(Number(slider.value)));
    refresh();
    $("layers").append(label);
  }

  const routeFile = await (await fetch("/data/route_example.geojson")).json();
  const route = routeFile.features[0].geometry.coordinates;
  // Dark casing under the dashes keeps the route readable on the orange terrain
  const routeLine = route.map(([x, y]) => [y, x]);
  L.polyline(routeLine, { color: "#14110f", weight: 6, opacity: 0.7 }).addTo(map);
  L.polyline(routeLine, { color: "#ffffff", weight: 3, dashArray: "6 6" }).addTo(map);
  const goal = route[route.length - 1];
  L.circleMarker([goal[1], goal[0]], { radius: 7, color: "#ff8a3d", fillOpacity: 0.3 })
    .bindTooltip("Science target").addTo(map);

  const astronautTrail = L.polyline([], { color: "#5fd4ff", weight: 2, opacity: 0.8 }).addTo(map);
  const roverTrail = L.polyline([], { color: "#ffd23d", weight: 2, opacity: 0.6 }).addTo(map);
  const astronautMarker = L.circleMarker([0, 0], { radius: 6, color: "#fff", weight: 2, fillColor: "#5fd4ff", fillOpacity: 1 });
  const roverMarker = L.marker([0, 0], {
    icon: L.divIcon({
      className: "rover-icon", iconSize: [22, 22],
      html: '<svg viewBox="-11 -11 22 22" width="22" height="22"><path d="M9 0 -7 -7 -3 0 -7 7Z" fill="currentColor" stroke="#000" stroke-width="1"/></svg>',
    }),
  });

  // Grids for the readouts; the map works without them
  const grids = {};
  for (const name of ["slope", "sky_view"]) {
    loadGrid(`/data/layers/${name}.npy`).then((grid) => { grids[name] = grid; });
  }

  const readout = L.control({ position: "bottomleft" });
  readout.onAdd = () => L.DomUtil.create("div", "cursor-readout");
  readout.addTo(map);
  map.on("mousemove", (event) => {
    const x = event.latlng.lng, y = event.latlng.lat;
    const slope = sample(grids.slope, cell, x, y);
    readout.getContainer().textContent = slope === null
      ? "" : `x ${fmt(x)} m · y ${fmt(y)} m · slope ${fmt(slope, 1)}°`;
  });

  function pushTrail(trail, x, y) {
    const points = trail.getLatLngs();
    const last = points[points.length - 1];
    if (last && Math.hypot(last.lng - x, last.lat - y) < 0.5) return;
    trail.addLatLng([y, x]);
    if (points.length > TRAIL_POINTS) trail.setLatLngs(points.slice(-TRAIL_POINTS));
  }

  function show(message) {
    $("link").className = `pill ${message.live ? "online" : "offline"}`;
    $("link").textContent = message.live ? "Live from ROS 2" : "No telemetry";

    if (message.t !== null) {
      const seconds = Math.floor(message.t);
      $("clock").textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
    }

    const astronaut = message.astronaut;
    if (astronaut) {
      astronautMarker.setLatLng([astronaut.y, astronaut.x]).addTo(map);
      pushTrail(astronautTrail, astronaut.x, astronaut.y);
      $("astronaut-position").textContent = `${fmt(astronaut.x)} m E, ${fmt(astronaut.y)} m N`;
      $("astronaut-elevation").textContent = `${fmt(terrain.elevation_of_z0_m + astronaut.z)} m`;
      $("astronaut-heading").textContent = `${fmt(((90 - astronaut.heading_deg) % 360 + 360) % 360)}°`;
      const slope = sample(grids.slope, cell, astronaut.x, astronaut.y);
      const sky = sample(grids.sky_view, cell, astronaut.x, astronaut.y);
      $("astronaut-slope").textContent = slope === null ? "–" : `${fmt(slope, 1)}°`;
      $("astronaut-sky").textContent = sky === null ? "–" : `${fmt(sky * 100)} %`;
      const { walked, total } = routeProgress(route, astronaut.x, astronaut.y);
      $("progress").style.width = `${(100 * walked) / total}%`;
      $("progress-text").textContent = `${fmt(walked)} of ${fmt(total)} m`;
    }

    const rover = message.rover;
    if (rover) {
      roverMarker.setLatLng([rover.y, rover.x]).addTo(map);
      const arrow = roverMarker.getElement()?.querySelector("svg");
      if (arrow) arrow.style.transform = `rotate(${-rover.heading_deg}deg)`;
      pushTrail(roverTrail, rover.x, rover.y);
      $("rover-state").textContent = rover.state ?? "–";
      $("rover-position").textContent = `${fmt(rover.x)} m E, ${fmt(rover.y)} m N`;
      $("rover-distance").textContent = `${fmt(message.rover_distance_m, 1)} m`;
    }
  }

  function connect() {
    const socket = new WebSocket(`ws://${location.host}/ws`);
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

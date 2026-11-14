// Helmet HUD: the next target, a direction arrow, oxygen, the way back and the alerts.
// Same WebSocket and endpoints as the dashboard; nothing here is sent back to ROS 2.

const $ = (id) => document.getElementById(id);
const fmt = (value, digits = 0) => value.toFixed(digits);
const compass = (headingDeg) => (((90 - headingDeg) % 360) + 360) % 360; // north = +y, as the dashboard
const bearing = (from, to) => (Math.atan2(to[0] - from[0], to[1] - from[1]) * 180) / Math.PI; // compass degrees
const wrap = (deg) => ((deg + 540) % 360) - 180;

let plan = null;
let planVersion = null;

async function loadPlan() {
  try {
    plan = await (await fetch("/mission")).json();
  } catch {
    plan = null;
  }
}

// The next target: the first one in walking order that the progress does not list as done
function nextTarget(progress) {
  if (!plan?.ok || !plan.targets?.length) return null;
  if (progress?.target) {
    const named = plan.targets.find((t) => t.name === progress.target);
    if (named) return named;
  }
  return plan.targets[0];
}

function show(message) {
  if (message.mission && message.mission !== planVersion) {
    planVersion = message.mission;
    loadPlan();
  }
  const live = Boolean(message.live);
  $("task").className = `task ${live ? "" : "bad"}`;
  $("clock").textContent = message.t === null ? "--:--" : `${String(Math.floor(message.t / 60)).padStart(2, "0")}:${String(Math.floor(message.t % 60)).padStart(2, "0")}`;

  const progress = message.mission_progress;
  const target = nextTarget(progress);
  const a = message.astronaut;

  if (!live || !a) {
    $("task").textContent = "No telemetry";
    $("target-line").textContent = "–";
    $("distance").textContent = "–";
    return;
  }

  // Task line: what the crew is doing now, from the mission progress
  if (progress?.phase === "working") {
    $("task").textContent = progress.executor?.startsWith("arm")
      ? `Rover arm: ${progress.target}`
      : `Working: ${progress.target}`;
    $("target-line").textContent = `${progress.work_left_s} s left`;
  } else if (progress?.phase === "waiting for rover") {
    $("task").textContent = `Waiting for the rover arm`;
    $("target-line").textContent = progress.target;
  } else if (progress?.phase === "returning") {
    $("task").textContent = "Returning to the crew rover";
    $("target-line").textContent = "";
  } else if (progress?.phase === "done") {
    $("task").textContent = "Mission complete";
    $("target-line").textContent = "";
  } else if (target) {
    $("task").textContent = `Next: ${target.name}`;
    $("target-line").textContent = target.why ?? "";
  } else {
    $("task").textContent = "Free walk";
    $("target-line").textContent = "";
  }

  // Arrow and distance to the next target, relative to where the astronaut faces
  if (target?.stop) {
    const to = target.stop;
    const dist = Math.hypot(to[0] - a.x, to[1] - a.y);
    const rel = wrap(bearing([a.x, a.y], to) - compass(a.heading_deg));
    $("arrow").style.transform = `rotate(${rel}deg)`;
    $("distance").textContent = dist < 15 ? "HERE" : `${fmt(dist)} m`;
  } else {
    $("distance").textContent = "–";
  }

  // Oxygen and the way back
  const suit = message.suit;
  if (suit && suit.o2_pct !== undefined) {
    $("o2").textContent = `${fmt(suit.o2_pct)} %`;
    $("o2").className = `value ${suit.turn_back ? "bad" : suit.o2_pct < 30 ? "warn" : "good"}`;
    $("o2-margin").textContent = `margin ${fmt(suit.margin_min)} min`;
    $("o2-margin").className = `small ${suit.turn_back ? "bad" : ""}`;
    $("alert").hidden = !suit.turn_back;
    if (suit.dose_rate_uSv_h !== undefined) $("dose").textContent = `dose ${fmt(suit.dose_rate_uSv_h, 1)} µSv/h · ${fmt(suit.dose_uSv, 2)} µSv`;
  }

  // Rover: where it is relative to the crew
  const r = message.rover;
  if (r) {
    $("rover").textContent = `${fmt(message.rover_distance_m, 1)} m`;
    $("rover-state").textContent = r.state ?? "–";
  }
}

function connect() {
  const socket = new WebSocket(`ws://${location.host}/ws`);
  socket.onmessage = (event) => show(JSON.parse(event.data));
  socket.onclose = () => {
    $("task").textContent = "Server offline";
    $("task").className = "task bad";
    setTimeout(connect, 1500);
  };
}

loadPlan();
connect();

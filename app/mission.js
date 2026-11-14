// Mission tab: the science EVA planned by ros/mission_planner.py, from /mission/plan.

const $ = (id) => document.getElementById(id);
const esc = (text) => String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const TOOL_NAMES = {};

export async function loadToolNames() {
  try {
    const catalog = await (await fetch("/app/rover_catalog.json")).json();
    for (const item of catalog.equipment) TOOL_NAMES[item.id] = item.name;
  } catch { /* names fall back to ids */ }
}

const minutes = (m) => (m >= 60 ? `${Math.floor(m / 60)} h ${String(Math.round(m % 60)).padStart(2, "0")} min` : `${Math.round(m)} min`);

export function renderMission(plan) {
  if (!plan?.ok) {
    $("mission-body").innerHTML = `<p class="note">${plan ? "No target fits the oxygen budget." : "Waiting for /mission/plan from ROS 2."}</p>`;
    return;
  }
  const t = plan.totals;
  const executorLabel = (e) => ({ astronaut: "Astronaut", arm: "Rover arm", "astronaut + rover": "Astronaut + rover", "arm + rover": "Rover arm + rover" })[e] ?? e;
  const targets = plan.targets.map((target, i) => `
    <li class="target">
      <div class="target-head">
        <span class="badge">${i + 1}</span>
        <b>${esc(target.name)}</b>
        <span class="exec exec-${target.executor.replace(/[^a-z]+/g, "-")}">${executorLabel(target.executor)}</span>
      </div>
      <p>${esc(target.why)}</p>
      <ul class="tasks">${target.tasks.map((task) => `<li>${esc(task)}</li>`).join("")}</ul>
      <p class="meta">${target.minutes} min on site · slope ${target.slope_deg}°${target.executor.startsWith("arm") ? ` · astronaut stops ${target.reach_m} m away` : ""}
        · tools: ${target.tools.map((tool) => esc(TOOL_NAMES[tool] ?? tool)).join(", ")}</p>
      ${target.warnings.map((w) => `<p class="warn">⚠ ${esc(w)}</p>`).join("")}
    </li>`).join("");
  const names = Object.fromEntries(plan.targets.map((target, i) => [target.id, `${i + 1}. ${target.name}`]));
  names.start = plan.start.name;
  const timeline = plan.timeline.map((leg) => `
    <tr><td>${esc(names[leg.from])} → ${esc(names[leg.to])}</td><td>${leg.length_m} m</td>
      <td>${leg.walk_min} min</td><td>${leg.work_min ? `${leg.work_min} min` : "–"}</td><td>${minutes(leg.arrive_min)}</td></tr>`).join("");

  $("mission-body").innerHTML = `
    <h1 class="mission-title">${esc(plan.name)}</h1>
    <p class="objective">${esc(plan.objective)}</p>
    <details><summary>Why boxwork</summary><p>${esc(plan.background)}</p><p class="note">${esc(plan.site_note)}</p></details>
    <div class="cards">
      <div class="card"><span>EVA time</span><b>${minutes(t.eva_min)}</b></div>
      <div class="card"><span>Walking</span><b>${(t.walk_m / 1000).toFixed(1)} km</b></div>
      <div class="card ${t.o2_margin_min < 30 ? "bad" : ""}"><span>Oxygen margin</span><b>${minutes(t.o2_margin_min)}</b></div>
      <div class="card"><span>Expected dose</span><b>${t.dose_uSv} µSv</b></div>
    </div>
    <p class="note">Support rover: ${plan.rover ? esc(plan.rover) : "none chosen yet (Rover planner tab)"} ·
      oxygen counted with a 30 min reserve${plan.dropped.length ? ` · dropped for oxygen: ${plan.dropped.map((d) => esc(d.name)).join(", ")}` : ""}</p>
    <h2>Targets in walking order</h2>
    <ol class="targets">${targets}</ol>
    <h2>Timeline</h2>
    <table class="timeline"><thead><tr><th>Leg</th><th>Distance</th><th>Walk</th><th>Work</th><th>Arrive / done</th></tr></thead>
      <tbody>${timeline}</tbody></table>`;
}

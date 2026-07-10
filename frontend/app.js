let gid = null;
let st = null;
let map = null;
let track = null;
let chart = null;
let previewTimer = null;

const $ = (id) => document.getElementById(id);

function fmtTime(s) {
  s = Math.round(s);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function initMap(series) {
  if (!map) {
    map = L.map("map", { zoomControl: false, attributionControl: false });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 17, opacity: 0.55,
    }).addTo(map);
  }
  const latlngs = series.lat.map((la, i) => [la, series.lon[i]]);
  if (track) track.setLatLngs(latlngs);
  else track = L.polyline(latlngs, { color: "#ff5c33", weight: 3.5, opacity: 0.9 }).addTo(map);
  map.fitBounds(track.getBounds(), { padding: [24, 24] });
}

function renderChart(series) {
  const data = {
    labels: series.t.map((t) => fmtTime(t)),
    datasets: [
      {
        label: "Speed km/h", data: series.v_kmh, yAxisID: "y",
        borderColor: "#ff5c33", borderWidth: 1.6, pointRadius: 0, tension: 0.3,
      },
      {
        label: "Elevation m", data: series.ele, yAxisID: "y1",
        borderColor: "#4a5568", borderWidth: 1, pointRadius: 0,
        backgroundColor: "rgba(139,148,167,0.15)", fill: true, tension: 0.3,
      },
      {
        label: "HR bpm", data: series.hr, yAxisID: "y",
        borderColor: "#ffb03a", borderWidth: 1.2, pointRadius: 0, tension: 0.3,
      },
    ],
  };
  if (chart) {
    chart.data = data;
    chart.update("none");
    return;
  }
  chart = new Chart($("chart"), {
    type: "line",
    data,
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: "#8b94a7", boxWidth: 12, font: { size: 10 } } } },
      scales: {
        x: { ticks: { color: "#5b6474", maxTicksLimit: 8, font: { size: 10 } }, grid: { color: "#1b2230" } },
        y: { ticks: { color: "#8b94a7", font: { size: 10 } }, grid: { color: "#1b2230" } },
        y1: { position: "right", ticks: { color: "#5b6474", font: { size: 10 } }, grid: { display: false } },
      },
    },
  });
}

function currentOps() {
  const ops = [];
  document.querySelectorAll(".tool").forEach((el) => {
    const enabled = el.querySelector(".tool-toggle").checked;
    if (!enabled) return;
    const params = {};
    el.querySelectorAll("[data-name]").forEach((r) => {
      if (r.dataset.kind === "checkbox") params[r.dataset.name] = r.checked;
      else if (r.dataset.kind === "select") params[r.dataset.name] = r.value;
      else params[r.dataset.name] = parseFloat(r.value);
    });
    ops.push({ tool: el.dataset.tool, params });
  });
  return ops;
}

function paramControl(p) {
  if (p.type === "select") {
    const opts = p.options.map((o) => `<option value="${o}">${o}</option>`).join("");
    return `<div class="param"><span>${p.label}</span>
      <select data-name="${p.name}" data-kind="select">${opts}</select></div>`;
  }
  if (p.type === "checkbox") {
    return `<div class="param param-check"><span>${p.label}</span>
      <input type="checkbox" data-name="${p.name}" data-kind="checkbox"
             ${p.default ? "checked" : ""}></div>`;
  }
  return `<div class="param"><span>${p.label}</span>
    <input type="range" data-name="${p.name}" data-kind="range" min="${p.min}" max="${p.max}"
           step="${p.step}" value="${p.default}">
    <span class="val">${p.default}</span></div>`;
}

function renderTools(tools) {
  const wrap = $("tools");
  wrap.innerHTML = "";
  tools.forEach((t) => {
    const div = document.createElement("div");
    div.className = "tool";
    div.dataset.tool = t.name;
    let html = `<label class="head"><input type="checkbox" class="tool-toggle"> ${t.label}</label>
      <div class="hint">${t.hint}</div>`;
    (t.params || []).forEach((p) => { html += paramControl(p); });
    div.innerHTML = html;
    wrap.appendChild(div);
  });
  wrap.querySelectorAll("input, select").forEach((inp) => {
    const evt = inp.tagName === "SELECT" ? "change" : "input";
    inp.addEventListener(evt, (e) => {
      if (e.target.dataset.kind === "range") {
        e.target.parentElement.querySelector(".val").textContent = e.target.value;
      }
      schedulePreview();
    });
  });
}

function updateTimes(stats, rivalTime) {
  $("rival-time").textContent = fmtTime(rivalTime);
  $("your-time").textContent = fmtTime(stats.elapsed_s);
  const d = rivalTime - stats.elapsed_s;
  const el = $("delta");
  if (d > 0) {
    el.textContent = `${fmtTime(d)} ahead of the crown`;
    el.className = "delta ahead";
  } else {
    el.textContent = `${fmtTime(-d)} short of the crown`;
    el.className = "delta behind";
  }
}

function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    const p = await api(`/api/games/${gid}/preview`, { ops: currentOps() });
    updateTimes(p.stats, p.rival_time_s);
    renderChart(p.series);
    initMap(p.series);
  }, 250);
}

function renderState() {
  if (st.state === "finished") {
    $("level-kicker").textContent = "THE END";
    $("level-title").textContent = "Every crown taken.";
    $("level-brief").textContent = "You beat every audit. Nobody knows. You know.";
    $("upload-btn").disabled = true;
    return;
  }
  const lv = st.level;
  $("scoreboard").innerHTML = `crowns <b>${st.wins.length}</b> · flags <b>${st.flags}</b>`;
  $("level-kicker").textContent = `LEVEL ${lv.id} — ${lv.segment_name} (${(lv.length_m / 1000).toFixed(1)} km)`;
  $("level-title").textContent = lv.title;
  $("level-brief").textContent = lv.brief;
  $("level-taunt").textContent = lv.taunt;
  $("level-intel").textContent = lv.intel;
  $("rival-name").textContent = `${lv.rival} (crown)`;
  renderTools(lv.tools);
  updateTimes(st.honest_stats, lv.rival_time_s);
  renderChart(st.series);
  initMap(st.series);
}

const LABELS = {
  win: "CROWN TAKEN", caught: "FLAGGED", too_slow: "TOO SLOW",
  under_review: "MANUAL REVIEW", withdrawn: "WITHDRAWN",
};

function renderChecks(checks) {
  const wrap = $("modal-checks");
  wrap.innerHTML = "";
  (checks || []).forEach((c) => {
    const div = document.createElement("div");
    div.className = `check ${c.passed ? "pass" : "fail"}`;
    div.innerHTML = `<div class="head"><span>${c.title}</span>
      <span class="status ${c.passed ? "pass" : "fail"}">${c.passed ? "PASS" : "FAIL"}</span></div>
      <div class="detail">${c.detail}</div>`;
    wrap.appendChild(div);
  });
}

function showModal(r) {
  const cls = r.outcome === "under_review" ? "too_slow" : r.outcome;
  $("modal-outcome").textContent = LABELS[r.outcome] || r.outcome;
  $("modal-outcome").className = `outcome ${cls}`;
  $("modal-verdict").textContent = r.verdict;
  renderChecks(r.checks);

  const actions = $("modal-actions");
  actions.innerHTML = "";
  if (r.outcome === "under_review") {
    addAction("STAND PAT", "primary", () => reviewAction("stand"));
    addAction("EDIT THE FILE", "ghost", enterEditMode);
    addAction("WITHDRAW", "ghost", () => reviewAction("withdraw"));
  } else {
    addAction(r.outcome === "win" ? "NEXT SEGMENT" : "CONTINUE", "primary", closeModalAndRefresh);
  }
  $("modal").classList.remove("hidden");
}

function addAction(label, kind, fn) {
  const b = document.createElement("button");
  b.className = `modal-action ${kind}`;
  b.textContent = label;
  b.addEventListener("click", fn);
  $("modal-actions").appendChild(b);
}

async function closeModalAndRefresh() {
  $("modal").classList.add("hidden");
  st = await api(`/api/games/${gid}`);
  renderState();
}

async function reviewAction(action) {
  const r = await api(`/api/games/${gid}/review`, { action });
  showModal(r);
}

let editMode = false;
function enterEditMode() {
  editMode = true;
  $("modal").classList.add("hidden");
  document.body.classList.add("editing");
  $("upload-btn").textContent = "RE-UPLOAD EDITED FILE";
  $("level-taunt").textContent =
    "You're editing a file that's already under review. Whatever you change, the original is still on record.";
}

async function upload() {
  const btn = $("upload-btn");
  btn.disabled = true;
  try {
    const path = editMode ? "edit" : "upload";
    const r = await api(`/api/games/${gid}/${path}`, { ops: currentOps() });
    if (editMode) {
      editMode = false;
      document.body.classList.remove("editing");
      $("upload-btn").textContent = "UPLOAD RIDE";
    }
    showModal(r);
  } finally {
    btn.disabled = false;
  }
}

async function init() {
  st = await api("/api/games", {});
  gid = st.id;
  renderState();
  $("upload-btn").addEventListener("click", upload);
}

init();

let gid = null;
let st = null;
let map = null;
let track = null;
let chart = null;
let previewTimer = null;
let editMode = false;
let soundOn = true;
let howtoShown = false;
let currentTauntAudio = null;
let currentReportAudio = null;

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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

// Audio is always user-initiated (click a ▶ VOICE button); never autoplays.
function playClip(url, btn) {
  if (!url || !soundOn) return;
  try {
    const a = new Audio(url);
    if (btn) {
      btn.classList.add("playing");
      const clear = () => btn.classList.remove("playing");
      a.addEventListener("ended", clear);
      a.addEventListener("error", clear);
    }
    a.play().catch(() => { if (btn) btn.classList.remove("playing"); });
  } catch (e) { /* ignore */ }
}

/* ---------------- map + telemetry ---------------- */
function initMap(series) {
  if (!map) {
    map = L.map("map", { zoomControl: false, attributionControl: false });
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      maxZoom: 18, opacity: 0.9,
    }).addTo(map);
  }
  const latlngs = series.lat.map((la, i) => [la, series.lon[i]]);
  if (track) track.setLatLngs(latlngs);
  else track = L.polyline(latlngs, { color: "#FF7A38", weight: 3.5, opacity: 0.95 }).addTo(map);
  // container may have just become visible / resized — force a relayout
  map.invalidateSize();
  map.fitBounds(track.getBounds(), { padding: [26, 26] });
  setTimeout(() => { map.invalidateSize(); map.fitBounds(track.getBounds(), { padding: [26, 26] }); }, 60);
}

function renderChart(series) {
  const data = {
    labels: series.t.map((t) => fmtTime(t)),
    datasets: [
      { label: "Speed km/h", data: series.v_kmh, yAxisID: "y",
        borderColor: "#FF7A38", borderWidth: 1.8, pointRadius: 0, tension: 0.35 },
      { label: "Elevation m", data: series.ele, yAxisID: "y1",
        borderColor: "#3a4150", borderWidth: 1, pointRadius: 0,
        backgroundColor: "rgba(58,65,80,0.28)", fill: true, tension: 0.35 },
      { label: "HR bpm", data: series.hr, yAxisID: "y",
        borderColor: "#6FB3FF", borderWidth: 1.3, pointRadius: 0, tension: 0.35 },
    ],
  };
  if (chart) { chart.data = data; chart.update("none"); return; }
  const grid = "rgba(38,43,52,0.7)";
  const tick = { color: "#5A616D", font: { family: "JetBrains Mono", size: 9 } };
  chart = new Chart($("chart"), {
    type: "line", data,
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: {
        color: "#8B93A0", boxWidth: 10, boxHeight: 2,
        font: { family: "JetBrains Mono", size: 9 }, usePointStyle: false } } },
      scales: {
        x: { ticks: { ...tick, maxTicksLimit: 8 }, grid: { color: grid } },
        y: { ticks: tick, grid: { color: grid } },
        y1: { position: "right", ticks: tick, grid: { display: false } },
      },
    },
  });
}

/* ---------------- toolkit ---------------- */
function currentOps() {
  const ops = [];
  document.querySelectorAll(".tool").forEach((el) => {
    if (!el.querySelector(".tool-toggle").checked) return;
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
    return `<div class="param param-check">
      <input type="checkbox" data-name="${p.name}" data-kind="checkbox" ${p.default ? "checked" : ""}>
      <span>${p.label}</span></div>`;
  }
  return `<div class="param"><span>${p.label}</span>
    <input type="range" data-name="${p.name}" data-kind="range" min="${p.min}" max="${p.max}"
           step="${p.step}" value="${p.default}"><span class="val num">${p.default}</span></div>`;
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
      if (e.target.dataset.kind === "range")
        e.target.parentElement.querySelector(".val").textContent = e.target.value;
      schedulePreview();
    });
  });
}

function updateTimes(stats, rivalTime) {
  $("rival-time").textContent = fmtTime(rivalTime);
  $("your-time").textContent = fmtTime(stats.elapsed_s);
  const d = rivalTime - stats.elapsed_s;
  const el = $("delta");
  el.textContent = d > 0 ? `▲ ${fmtTime(d)} under` : `▼ ${fmtTime(-d)} over`;
  el.className = "mu-delta num " + (d > 0 ? "ahead" : "behind");
}

function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    const p = await api(`/api/games/${gid}/preview`, { ops: currentOps() });
    updateTimes(p.stats, p.rival_time_s);
    renderChart(p.series);
    initMap(p.series);
  }, 220);
}

/* ---------------- render play state ---------------- */
function renderState() {
  if (st.state === "finished") { showReport(); return; }
  const lv = st.level;
  $("rv-score").textContent = `${st.wins.length}–${st.flags}`;
  $("scoreboard").innerHTML =
    `<span class="crowns">CROWNS <b>${st.wins.length}</b></span>` +
    `<span class="flags">FLAGS <b>${st.flags}</b></span>`;
  $("level-kicker").textContent = `LEVEL ${lv.id} / 5 · ${lv.segment_name} · ${(lv.length_m / 1000).toFixed(1)} KM`;
  $("map-seg").textContent = lv.segment_name;
  $("level-title").textContent = lv.title;
  $("level-brief").textContent = lv.brief;
  $("level-taunt").textContent = (lv.taunt || "").replace(/^Dax:\s*'?|'$/g, "");
  $("taunt-mark").textContent = lv.rival || "DAX";
  $("level-intel").textContent = lv.intel;
  $("rival-name").textContent = `${lv.rival} · CROWN`;
  renderTools(lv.tools);
  updateTimes(st.honest_stats, lv.rival_time_s);
  renderChart(st.series);
  initMap(st.series);

  // objective line — always tells the player exactly what to do
  $("objective").innerHTML =
    `<span class="obj-tag">GOAL</span> You rode <b>${fmtTime(st.honest_stats.elapsed_s)}</b>. ` +
    `Dax's crown is <b>${fmtTime(lv.rival_time_s)}</b>. You can't ride faster — ` +
    `edit the file below to get <b>under his time</b>, then survive the audit.`;

  // taunt is click-to-hear, never autoplay
  currentTauntAudio = lv.taunt_audio || null;
  $("taunt-play").style.display = currentTauntAudio ? "" : "none";

  // draw the eye to the toolkit + upload on the first level
  $("upload-btn").classList.toggle("hint-pulse", lv.id === 1);
}

/* ---------------- audit scan overlay ---------------- */
function openAudit(title, sub) {
  $("audit-title").textContent = title;
  $("audit-sub").textContent = sub;
  $("audit-checks").innerHTML = "";
  $("audit-foot").classList.add("hidden");
  $("audit-actions").innerHTML = "";
  $("audit").classList.remove("hidden");
}

async function revealChecks(checks) {
  const wrap = $("audit-checks");
  for (const c of checks) {
    const row = document.createElement("div");
    row.className = "acheck scanning";
    row.innerHTML =
      `<div class="dot"></div>
       <div><div class="ac-title">${c.title}</div>
       <div class="ac-detail">analyzing…</div></div>
       <div class="ac-stamp">SCAN</div>`;
    wrap.appendChild(row);
    wrap.scrollTop = wrap.scrollHeight;
    await sleep(360);
    row.classList.remove("scanning");
    row.classList.add(c.passed ? "pass" : "fail");
    row.querySelector(".ac-detail").textContent = c.detail;
    row.querySelector(".ac-stamp").textContent = c.passed ? "PASS" : "FAIL";
    await sleep(180);
  }
}

const LABELS = {
  win: "CROWN TAKEN", caught: "FLAGGED", too_slow: "TOO SLOW",
  under_review: "MANUAL REVIEW", withdrawn: "WITHDRAWN",
};

function showOutcome(r) {
  const foot = $("audit-foot");
  const cls = r.outcome;
  $("audit-outcome").textContent = LABELS[cls] || cls;
  $("audit-outcome").className = "audit-outcome " + cls;
  $("audit-verdict").textContent = r.verdict || "";
  const actions = $("audit-actions");
  actions.innerHTML = "";
  if (r.outcome === "under_review") {
    addAction("STAND PAT", "primary", () => reviewAction("stand"));
    addAction("EDIT THE FILE", "ghost", enterEditMode);
    addAction("WITHDRAW", "ghost", () => reviewAction("withdraw"));
  } else {
    addAction(r.outcome === "win" ? "NEXT SEGMENT" : "BACK TO THE FILE", "primary", closeAuditAndRefresh);
  }
  foot.classList.remove("hidden");
  if (r.outcome === "caught") {
    document.body.classList.add("flag-flash");
    setTimeout(() => document.body.classList.remove("flag-flash"), 520);
  }
  $("audit-sub").textContent = "Audit complete.";
}

function addAction(label, kind, fn) {
  const b = document.createElement("button");
  b.className = kind === "primary" ? "btn-primary" : "btn-ghost";
  b.textContent = label;
  b.addEventListener("click", fn);
  $("audit-actions").appendChild(b);
}

async function closeAuditAndRefresh() {
  $("audit").classList.add("hidden");
  st = await api(`/api/games/${gid}`);
  renderState();
}

/* ---------------- submit flows ---------------- */
function showAuditError() {
  $("audit-sub").textContent = "Connection hiccup.";
  $("audit-outcome").textContent = "AUDIT INTERRUPTED";
  $("audit-outcome").className = "audit-outcome caught";
  $("audit-verdict").textContent =
    "The server didn't respond in time (it may have been reconnecting). " +
    "Close this and hit UPLOAD RIDE again — your ride edits are still set.";
  $("audit-actions").innerHTML = "";
  addAction("CLOSE", "primary", () => $("audit").classList.add("hidden"));
  $("audit-foot").classList.remove("hidden");
}

async function submitRun(path, body, title, sub) {
  openAudit(title, sub);
  await sleep(500);
  try {
    const r = await api(`/api/games/${gid}/${path}`, body);
    await revealChecks(r.checks || []);
    showOutcome(r);
    return r;
  } catch (e) {
    showAuditError();
    return null;
  }
}

async function upload() {
  const btn = $("upload-btn");
  btn.disabled = true;
  try {
    const editing = editMode;
    const r = await submitRun(
      editing ? "edit" : "upload",
      { ops: currentOps() },
      editing ? "RE-AUDIT · EDITED FILE" : "INTEGRITY AUDIT",
      editing ? "Re-examining the edited upload…" : "Running forensic checks…",
    );
    if (editing && r && r.outcome !== "under_review") {
      editMode = false;
      document.body.classList.remove("editing");
      $("upload-btn").textContent = "UPLOAD RIDE";
      $("audit-note").textContent = "Every upload is audited. There is no undo.";
    }
  } finally {
    btn.disabled = false;
  }
}

async function reviewAction(action) {
  try {
    if (action === "withdraw") {
      const r = await api(`/api/games/${gid}/review`, { action });
      $("audit-checks").innerHTML = "";
      showOutcome(r);
      return;
    }
    openAudit("MANUAL REVIEW", "A human reviewer re-runs the checks, tighter…");
    await sleep(500);
    const r = await api(`/api/games/${gid}/review`, { action });
    await revealChecks(r.checks || []);
    showOutcome(r);
  } catch (e) {
    showAuditError();
  }
}

function enterEditMode() {
  editMode = true;
  $("audit").classList.add("hidden");
  document.body.classList.add("editing");
  $("upload-btn").textContent = "RE-UPLOAD EDITED FILE";
  $("audit-note").textContent = "The original is already on record. Time Travel remembers.";
  $("level-taunt").textContent =
    "You're editing a file that's already under review. Whatever you change, the original still exists.";
  $("taunt-mark").textContent = "RISK";
}

/* ---------------- case file / report ---------------- */
async function showReport() {
  const rep = await api(`/api/games/${gid}/report`);
  $("report-stamp").textContent = rep.flags > 0 ? "FLAGGED" : "CASE CLOSED";
  $("report-title").textContent = rep.title;
  $("report-subtitle").textContent = rep.subtitle;
  const wrap = $("report-findings");
  wrap.innerHTML = "";
  $("report").classList.remove("hidden");
  currentReportAudio = rep.audio || null;
  $("report-play").style.display = currentReportAudio ? "" : "none";
  for (let i = 0; i < rep.findings.length; i++) {
    const f = rep.findings[i];
    const div = document.createElement("div");
    div.className = "rfinding";
    div.style.animationDelay = `${i * 120}ms`;
    div.innerHTML = `<div class="rf-seg">${f.segment}</div><div class="rf-text">${f.finding}</div>`;
    wrap.appendChild(div);
  }
  $("report-verdict").textContent = rep.verdict;
  $("report-tally").innerHTML =
    `CROWNS TAKEN <b>${rep.crowns}</b>&nbsp;&nbsp;·&nbsp;&nbsp;TIMES FLAGGED <b>${rep.flags}</b>` +
    `&nbsp;&nbsp;·&nbsp;&nbsp;REPORT BY <b>${rep.generated_by === "gemini" ? "GEMINI" : "CASE TEMPLATE"}</b>`;
  $("report-epilogue").textContent = rep.closing;
}

/* ---------------- boot ---------------- */
async function loadGame(retries = 2) {
  for (let i = 0; i <= retries; i++) {
    try {
      return await api("/api/games", {});
    } catch (e) {
      if (i === retries) throw e;
      await sleep(800);  // brief pause; Snowflake may be resuming its warehouse
    }
  }
}

async function start() {
  $("title").classList.add("hidden");
  // the how-to card doubles as the loading cover while the first game is created
  if (!howtoShown) { howtoShown = true; $("howto").classList.remove("hidden"); }
  try {
    st = await loadGame();
    gid = st.id;
    renderState();
  } catch (e) {
    $("objective").innerHTML =
      '<span class="obj-tag">ERROR</span> Could not reach the server — ' +
      'refresh the page to try again.';
  }
}

$("start-btn").addEventListener("click", start);
$("upload-btn").addEventListener("click", () => { $("upload-btn").classList.remove("hint-pulse"); upload(); });
$("howto-go").addEventListener("click", () => $("howto").classList.add("hidden"));
$("taunt-play").addEventListener("click", (e) => playClip(currentTauntAudio, e.currentTarget));
$("report-play").addEventListener("click", (e) => playClip(currentReportAudio, e.currentTarget));
$("sound-toggle").addEventListener("click", (e) => {
  soundOn = !soundOn;
  e.currentTarget.textContent = soundOn ? "SOUND ON" : "SOUND OFF";
  e.currentTarget.classList.toggle("off", !soundOn);
});

"use strict";
const SIM = /*__SIM_DATA__*/null;

// ---------- helpers ----------
const $ = (s) => document.querySelector(s);
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const SERIES_VARS = ["--s1","--s2","--s3","--s4","--s5","--s6","--s7","--s8"];
const fmt = (x, d = 2) => (x == null || Number.isNaN(x)) ? "–"
  : Math.abs(x) >= 1000 ? x.toLocaleString("en-US", { maximumFractionDigits: 0 })
  : x.toLocaleString("en-US", { maximumFractionDigits: d });
const el = (tag, attrs = {}, text) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  return e;
};
// SVG nodes need the SVG namespace — createElement("svg") renders nothing.
const svgEl = (tag, attrs = {}, text) => {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  return e;
};

// ---------- data prep ----------
// All trace-derived state is rebuilt by deriveState() so a live /api/run
// response can swap the whole run via reinit(payload).
let model, kpis, T_END, UNIT;
let blocks, entityTypes, entities, stepSeries, cum, poolOfService;

const typeColor = (ty) => {
  const i = entityTypes.indexOf(ty);
  return i >= 0 && i < 8 ? cssVar(SERIES_VARS[i]) : cssVar("--ink-3");
};

function renderHeader() {
  document.title = model.name + " — simulation";
  $("#title").textContent = model.name;
  $("#meta").textContent =
    `seed ${kpis.run.seed} · ${fmt(T_END, 0)} ${UNIT}` +
    (kpis.run.warmup ? ` · warmup ${fmt(kpis.run.warmup, 0)}` : "") +
    ` · ${SIM.trace.length.toLocaleString()} events`;
}

// Per-entity segments + per-block/pool step series, one pass in (t, seq) order.
function deriveState() {
  blocks = new Map(model.blocks.map((b) => [b.name, b]));
  // Entity types -> fixed categorical slots (alphabetical = deterministic).
  entityTypes = [...new Set(SIM.trace.filter((r) => r.entity_type).map((r) => r.entity_type))].sort();
  entities = new Map(); // id -> {type, segs:[{t0,block,unit}], end, endKind}
  stepSeries = {};      // name -> [[t, v], ...]
  cum = { arrivals: [[0, 0]], departures: [[0, 0]] };
  const bump = (name, t, dv, abs) => {
    const s = stepSeries[name] || (stepSeries[name] = [[0, 0]]);
    const v = abs != null ? abs : s[s.length - 1][1] + dv;
    s.push([t, v]);
  };
  poolOfService = {}; // block name -> pool name (for busy series naming)
  for (const b of model.blocks) if (b.type === "Service") poolOfService[b.name] = b.params.resource;

  for (const r of SIM.trace) {
    const t = r.t;
    if (r.entity_id != null && !entities.has(r.entity_id))
      entities.set(r.entity_id, { type: r.entity_type, segs: [], end: T_END, endKind: null });
    const E = r.entity_id != null ? entities.get(r.entity_id) : null;
    switch (r.event) {
      case "arrival":
        E.segs.push({ t0: t, block: r.block, unit: null });
        cum.arrivals.push([t, cum.arrivals[cum.arrivals.length - 1][1] + 1]);
        bump(`src:${r.block}`, t, +1);
        break;
      case "enter_block":
        E.segs.push({ t0: t, block: r.block, unit: null });
        break;
      case "seize":
        E.segs.push({ t0: t, block: r.block, unit: r.resource_unit });
        if (r.resource) bump(`pool:${r.resource}`, t, +1);
        break;
      case "release":
        if (r.resource) bump(`pool:${r.resource}`, t, -1);
        break;
      case "queue_join": bump(`queue:${r.block}`, t, 0, r.qlen); break;
      case "queue_leave": case "renege": if (r.qlen != null) bump(`queue:${r.block}`, t, 0, r.qlen); break;
      case "state": if (r.wip != null) bump("wip", t, 0, r.wip); break;
      case "depart":
        E.end = t; E.endKind = "depart";
        cum.departures.push([t, cum.departures[cum.departures.length - 1][1] + 1]);
        bump(`sink:${r.block}`, t, +1);
        break;
      case "balk": case "renege_drop": E.end = t; E.endKind = "drop"; break;
    }
  }
  // A renege that leads nowhere ends the entity (no further enter_block events).
  for (const [, E] of entities) if (E.endKind === null && E.segs.length === 0) E.end = 0;
}

const segAt = (E, t) => { // binary search the segment active at t
  const s = E.segs; let lo = 0, hi = s.length - 1, ans = -1;
  while (lo <= hi) { const mid = (lo + hi) >> 1; if (s[mid].t0 <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1; }
  return ans >= 0 ? s[ans] : null;
};
const valAt = (series, t) => {
  let lo = 0, hi = series.length - 1, ans = 0;
  while (lo <= hi) { const mid = (lo + hi) >> 1; if (series[mid][0] <= t) { ans = series[mid][1]; lo = mid + 1; } else hi = mid - 1; }
  return ans;
};

// ---------- tabs & theme ----------
document.querySelectorAll("nav.tabs button").forEach((b) =>
  b.addEventListener("click", () => {
    document.querySelectorAll("nav.tabs button").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === "panel-" + b.dataset.tab));
    if (b.dataset.tab === "charts") drawCharts();
    if (b.dataset.tab === "mc") drawMC();
  }));
$("#themeBtn").addEventListener("click", () => {
  const cur = document.documentElement.dataset.theme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  document.documentElement.dataset.theme = cur === "dark" ? "light" : "dark";
  drawCharts(); mcDirty = true; drawMC(true); draw();
});

// ---------- animation ----------
const canvas = $("#anim"), ctx = canvas.getContext("2d");
const BW = 118, BH = 60;
let simT = 0, playing = false, lastFrame = null;

let layout;
function computeLayout() {
  let maxX = 0, maxY = 0;
  for (const b of model.blocks) { maxX = Math.max(maxX, (b.x || 0) + BW); maxY = Math.max(maxY, (b.y || 0) + BH); }
  layout = { w: Math.max(maxX + 90, 640), h: Math.max(maxY + 90, 300) };
}
function sizeCanvas() {
  const dpr = window.devicePixelRatio || 1;
  canvas.width = layout.w * dpr; canvas.height = layout.h * dpr;
  canvas.style.width = layout.w + "px"; canvas.style.height = layout.h + "px";
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

const GLYPH = { Source: "▸", Sink: "◎", Queue: "☰", Delay: "◷", Service: "⚙", Route: "⑂", Assign: "✎", Seize: "⊕", Release: "⊖",
  Batch: "▣", Unbatch: "▤", Gate: "⊫", Move: "➝", Ride: "↕", TimeMeasureStart: "⏱", TimeMeasureEnd: "⏱" };
const center = (b) => ({ x: b.x + BW / 2, y: b.y + BH / 2 });

function draw() {
  ctx.clearRect(0, 0, layout.w, layout.h);
  ctx.fillStyle = cssVar("--surface-1");
  ctx.fillRect(0, 0, layout.w, layout.h);

  // Edges beneath blocks.
  ctx.strokeStyle = cssVar("--axis"); ctx.lineWidth = 1.2;
  for (const b of model.blocks) for (const tgt of Object.values(b.outputs)) {
    if (!tgt || !blocks.has(tgt)) continue;
    const a = center(b), c = center(blocks.get(tgt));
    ctx.beginPath(); ctx.moveTo(a.x + BW / 2 - 4, a.y); ctx.lineTo(c.x - BW / 2 + 2, c.y); ctx.stroke();
    const ang = Math.atan2(c.y - a.y, c.x - a.x), hx = c.x - BW / 2 + 2, hy = c.y;
    ctx.beginPath(); ctx.moveTo(hx, hy);
    ctx.lineTo(hx - 7 * Math.cos(ang - 0.4), hy - 7 * Math.sin(ang - 0.4));
    ctx.lineTo(hx - 7 * Math.cos(ang + 0.4), hy - 7 * Math.sin(ang + 0.4));
    ctx.closePath(); ctx.fillStyle = cssVar("--axis"); ctx.fill();
  }

  // Blocks.
  for (const b of model.blocks) {
    ctx.fillStyle = cssVar("--page");
    ctx.strokeStyle = cssVar("--border"); ctx.lineWidth = 1;
    roundRect(b.x, b.y, BW, BH, 10); ctx.fill(); ctx.stroke();
    ctx.fillStyle = cssVar("--ink-3"); ctx.font = "11px system-ui";
    let header = `${GLYPH[b.type] || "▢"} ${b.type}`;
    if (b.type === "Queue")
      header += ` · ${valAt(stepSeries[`queue:${b.name}`] || [[0, 0]], simT)}`;
    ctx.fillText(header, b.x + 8, b.y + 15);
    ctx.fillStyle = cssVar("--ink-1"); ctx.font = "600 12.5px system-ui";
    ctx.fillText(truncate(b.name, 15), b.x + 8, b.y + 31);
    ctx.font = "11px system-ui"; ctx.fillStyle = cssVar("--ink-2");
    if (b.type === "Source") ctx.fillText(`out: ${valAt(stepSeries[`src:${b.name}`] || [[0, 0]], simT)}`, b.x + 8, b.y + 48);
    if (b.type === "Sink") ctx.fillText(`in: ${valAt(stepSeries[`sink:${b.name}`] || [[0, 0]], simT)}`, b.x + 8, b.y + 48);
    if (b.type === "Service") {
      const busy = valAt(stepSeries[`pool:${b.params.resource}`] || [[0, 0]], simT);
      const cap = b.params.capacity;
      for (let i = 0; i < Math.min(cap, 8); i++) {
        ctx.beginPath(); ctx.arc(b.x + 12 + i * 13, b.y + 47, 4.5, 0, 7);
        if (i < busy) { ctx.fillStyle = cssVar("--s1"); ctx.fill(); }
        else { ctx.strokeStyle = cssVar("--axis"); ctx.lineWidth = 1.4; ctx.stroke(); }
      }
      if (cap > 8) { ctx.fillStyle = cssVar("--ink-3"); ctx.fillText(`${busy}/${cap}`, b.x + 12 + 8 * 13, b.y + 50); }
    }
  }

  // Entities: group the alive ones by block, then position within it.
  const byBlock = new Map();
  for (const [id, E] of entities) {
    if (E.end <= simT) continue;
    const seg = segAt(E, simT);
    if (!seg) continue;
    if (!byBlock.has(seg.block)) byBlock.set(seg.block, []);
    byBlock.get(seg.block).push({ id, E, seg });
  }
  const TRAVEL = T_END / 600; // visual tween window after entering a block
  for (const [bname, list] of byBlock) {
    const b = blocks.get(bname); if (!b) continue;
    list.sort((p, q) => p.seg.t0 - q.seg.t0 || p.id - q.id);
    list.forEach((item, i) => {
      let px, py;
      if (b.type === "Queue") { // waiting row inside the block, head at right
        const k = Math.min(i, 7);
        px = b.x + BW - 14 - k * 13; py = b.y + 47;
        if (i === 8) { ctx.fillStyle = cssVar("--ink-3"); ctx.font = "10px system-ui"; ctx.fillText(`+${list.length - 8}`, b.x + 4, py + 3); }
        if (i >= 8) return;
      } else if (b.type === "Service" && item.seg.unit) {
        const unitIdx = parseInt(String(item.seg.unit).split("#")[1] || "1", 10) - 1;
        px = b.x + 12 + Math.min(unitIdx, 7) * 13; py = b.y + 47;
      } else {
        const k = Math.min(i, 5);
        px = center(b).x + (k % 3) * 12 - 12; py = center(b).y + Math.floor(k / 3) * 12 - 4;
      }
      // Tween in from the previous block just after a transition.
      const segIdx = item.E.segs.indexOf(item.seg);
      if (segIdx > 0 && simT - item.seg.t0 < TRAVEL) {
        const prev = blocks.get(item.E.segs[segIdx - 1].block);
        if (prev) {
          const f = (simT - item.seg.t0) / TRAVEL, a = center(prev);
          px = a.x + (px - a.x) * f; py = a.y + (py - a.y) * f;
        }
      }
      ctx.beginPath(); ctx.arc(px, py, 5, 0, 7);
      ctx.fillStyle = typeColor(item.E.type); ctx.fill();
      ctx.lineWidth = 2; ctx.strokeStyle = cssVar("--surface-1"); ctx.stroke();
    });
  }
  $("#clock").textContent = `t = ${fmt(simT, 1)} ${UNIT} · in system: ${valAt(stepSeries.wip || [[0, 0]], simT)}`;
  $("#scrub").value = Math.round((simT / T_END) * 1000);
}
function roundRect(x, y, w, h, r) {
  ctx.beginPath(); ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
const truncate = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

// Playback: slider is log-scaled between T/600 and T/2 sim-units per real second.
const speedOf = () => (T_END / 600) * Math.pow(300, $("#speed").value / 100);
function tick(ts) {
  if (playing) {
    if (lastFrame != null) {
      simT = Math.min(simT + ((ts - lastFrame) / 1000) * speedOf(), T_END);
      if (simT >= T_END) setPlaying(false);
    }
    draw();
  }
  lastFrame = ts;
  requestAnimationFrame(tick);
}
function setPlaying(p) { playing = p; $("#playBtn").textContent = p ? "❚❚ Pause" : "▶ Play"; }
$("#playBtn").addEventListener("click", () => { if (simT >= T_END) simT = 0; setPlaying(!playing); });
$("#stepBtn").addEventListener("click", () => { setPlaying(false); simT = Math.min(simT + speedOf() / 10, T_END); draw(); });
$("#resetBtn").addEventListener("click", () => { setPlaying(false); simT = 0; draw(); });
$("#scrub").addEventListener("input", (e) => { setPlaying(false); simT = (e.target.value / 1000) * T_END; draw(); });

// ---------- charts (SVG, crosshair tooltip, drawn to the playhead) ----------
const tooltip = $("#tooltip");
function chart(container, title, seriesDefs) {
  // seriesDefs: [{name, data: [[t, v]...], color}]
  const card = el("div", { class: "card chart-card" });
  card.appendChild(el("h3", {}, title));
  if (seriesDefs.length > 1) {
    const lg = el("div", { class: "legend" });
    for (const s of seriesDefs) {
      const item = el("span");
      const key = el("span", { class: "key" }); key.style.borderTopColor = s.color;
      item.appendChild(key); item.appendChild(document.createTextNode(s.name));
      lg.appendChild(item);
    }
    card.appendChild(lg);
  }
  const W = Math.min(container.clientWidth - 34, 1060) || 900, H = 220,
    m = { l: 46, r: 14, t: 8, b: 22 };
  const svg = svgEl("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` });
  const ymax = Math.max(1, ...seriesDefs.flatMap((s) => s.data.map((p) => p[1]))) * 1.08;
  const X = (t) => m.l + (t / T_END) * (W - m.l - m.r);
  const Y = (v) => H - m.b - (v / ymax) * (H - m.t - m.b);
  // Grid + ticks (clean numbers).
  const yticks = niceTicks(0, ymax, 4);
  for (const v of yticks) {
    const ln = svgEl("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), stroke: "var(--grid)", "stroke-width": 1 });
    svg.appendChild(ln);
    svg.appendChild(svgEl("text", { x: m.l - 6, y: Y(v) + 4, "text-anchor": "end" }, fmt(v, 0)));
  }
  for (const t of niceTicks(0, T_END, 6))
    svg.appendChild(svgEl("text", { x: X(t), y: H - 6, "text-anchor": "middle" }, fmt(t, 0)));
  svg.appendChild(svgEl("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, stroke: "var(--axis)", "stroke-width": 1 }));
  // Step paths.
  for (const s of seriesDefs) {
    let d = "";
    for (let i = 0; i < s.data.length; i++) {
      const [t, v] = s.data[i];
      d += (i === 0 ? `M ${X(t)} ${Y(v)}` : ` H ${X(t)} V ${Y(v)}`);
    }
    d += ` H ${X(T_END)}`;
    const p = svgEl("path", { d, fill: "none", stroke: s.color, "stroke-width": 2,
      "stroke-linejoin": "round", "stroke-linecap": "round" });
    svg.appendChild(p);
    s._path = p;
  }
  // Playhead clip + crosshair.
  const cross = svgEl("line", { y1: m.t, y2: H - m.b, stroke: "var(--axis)", "stroke-width": 1, visibility: "hidden" });
  svg.appendChild(cross);
  const hit = svgEl("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" });
  svg.appendChild(hit);
  hit.addEventListener("pointermove", (evt) => {
    const r = svg.getBoundingClientRect();
    const t = Math.max(0, Math.min(T_END, ((evt.clientX - r.left) - m.l) / (W - m.l - m.r) * T_END));
    cross.setAttribute("x1", X(t)); cross.setAttribute("x2", X(t));
    cross.setAttribute("visibility", "visible");
    tooltip.style.display = "block";
    tooltip.textContent = "";
    tooltip.appendChild(el("div", { class: "tt-t" }, `t = ${fmt(t, 1)} ${UNIT}`));
    for (const s of seriesDefs) {
      const row = el("div", { class: "row" });
      const key = el("span", { class: "key" }); key.style.borderTopColor = s.color;
      row.appendChild(key);
      row.appendChild(el("span", {}, s.name));
      row.appendChild(el("b", {}, fmt(valAt(s.data, t), 0)));
      tooltip.appendChild(row);
    }
    tooltip.style.left = Math.min(evt.clientX + 14, innerWidth - 170) + "px";
    tooltip.style.top = (evt.clientY + 12) + "px";
  });
  hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); tooltip.style.display = "none"; });
  card.appendChild(svg);
  container.appendChild(card);
}
function niceTicks(lo, hi, n) {
  const span = hi - lo, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 5, 10].map((k) => k * mag).find((s) => span / s <= n) || 10 * mag;
  const out = []; for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(v);
  return out;
}
function drawCharts() {
  const root = $("#charts"); root.textContent = "";
  const S = (i) => cssVar(SERIES_VARS[i % 8]);
  if (stepSeries.wip) chart(root, `Entities in system (WIP) — ${UNIT}`, [{ name: "WIP", data: stepSeries.wip, color: S(0) }]);
  const queues = Object.keys(stepSeries).filter((k) => k.startsWith("queue:"));
  if (queues.length) chart(root, "Queue length", queues.map((k, i) => ({ name: k.slice(6), data: stepSeries[k], color: S(i) })));
  const pools = Object.keys(stepSeries).filter((k) => k.startsWith("pool:"));
  if (pools.length) chart(root, "Busy resource units", pools.map((k, i) => ({ name: k.slice(5), data: stepSeries[k], color: S(i) })));
  chart(root, "Cumulative flow", [
    { name: "arrivals", data: cum.arrivals, color: S(0) },
    { name: "departures", data: cum.departures, color: S(2) },
  ]);
}

// ---------- monte carlo ----------
// MC holds the current replication result: either the embedded experiment
// (static viewers) or the response of POST /api/replicate (live mode).
// Shape: {n, confidence, kpi_table, kpi_samples, percentiles, source}
let MC = null, mcDirty = true;

function seedMC() {
  const ex = SIM.experiment;
  if (ex && ex.kpi_samples) {
    MC = {
      n: ex.n_replications, confidence: ex.confidence, kpi_table: ex.kpi_table,
      kpi_samples: ex.kpi_samples, percentiles: ex.percentiles, source: "embedded",
    };
  }
  $("#mcTabBtn").hidden = !(SIM.live || MC);
  mcDirty = true;
}

function quantile(sorted, q) {
  if (!sorted.length) return NaN;
  const pos = (sorted.length - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

// Histogram of per-replication KPI values. Single series (one hue); the
// mean±CI band and P10/P50/P90 reference lines are overlays, not series.
function histogram(container, title, samples, opts = {}) {
  const vals = samples.filter((v) => v != null && !Number.isNaN(v)).sort((a, b) => a - b);
  const card = el("div", { class: "card chart-card" });
  card.appendChild(el("h3", {}, title));
  container.appendChild(card);
  if (!vals.length) { card.appendChild(el("div", { class: "note" }, "no data")); return; }
  const lo = vals[0], hi = vals[vals.length - 1];
  if (lo === hi) {
    card.appendChild(el("div", { class: "note" }, `constant across replications: ${fmt(lo, 3)}`));
    return;
  }
  // Freedman–Diaconis, Sturges fallback, clamped to [5, 40] bins.
  const iqr = quantile(vals, 0.75) - quantile(vals, 0.25);
  const width = iqr > 0 ? 2 * iqr / Math.cbrt(vals.length) : (hi - lo) / (Math.ceil(Math.log2(vals.length)) + 1);
  const nBins = Math.max(5, Math.min(40, Math.round((hi - lo) / width) || 5));
  const counts = new Array(nBins).fill(0);
  for (const v of vals) counts[Math.min(nBins - 1, Math.floor(((v - lo) / (hi - lo)) * nBins))]++;
  const maxCount = Math.max(...counts);

  const W = Math.max(280, Math.min((card.clientWidth || 460) - 34, 1060)), H = 210,
    m = { l: 40, r: 14, t: 20, b: 22 };
  const svg = svgEl("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` });
  const X = (v) => m.l + ((v - lo) / (hi - lo)) * (W - m.l - m.r);
  const Y = (c) => H - m.b - (c / (maxCount * 1.08)) * (H - m.t - m.b);
  for (const c of niceTicks(0, maxCount, 3)) {
    svg.appendChild(svgEl("line", { x1: m.l, x2: W - m.r, y1: Y(c), y2: Y(c), stroke: "var(--grid)", "stroke-width": 1 }));
    svg.appendChild(svgEl("text", { x: m.l - 6, y: Y(c) + 4, "text-anchor": "end" }, fmt(c, 0)));
  }
  for (const v of niceTicks(lo, hi, 5))
    svg.appendChild(svgEl("text", { x: X(v), y: H - 6, "text-anchor": "middle" }, fmt(v, 2)));
  svg.appendChild(svgEl("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, stroke: "var(--axis)", "stroke-width": 1 }));

  // CI band + mean line beneath the bars' tops but above grid.
  const s = opts.summary;
  if (s && s.ci_low != null && !Number.isNaN(s.ci_low)) {
    svg.appendChild(svgEl("rect", {
      x: X(Math.max(lo, s.ci_low)), y: m.t,
      width: Math.max(1, X(Math.min(hi, s.ci_high)) - X(Math.max(lo, s.ci_low))),
      height: H - m.t - m.b, fill: cssVar("--s2"), "fill-opacity": 0.1,
    }));
  }
  // Bars: ≤24px thick, 2px surface gap, rounded data-end / square baseline.
  const slotW = (W - m.l - m.r) / nBins;
  const barW = Math.min(24, Math.max(1.5, slotW - 2));
  counts.forEach((c, i) => {
    if (!c) return;
    const x = m.l + i * slotW + (slotW - barW) / 2, y = Y(c), h = H - m.b - y;
    const r = Math.min(4, barW / 2, h);
    const bar = svgEl("path", {
      d: `M ${x} ${y + h} L ${x} ${y + r} Q ${x} ${y} ${x + r} ${y} L ${x + barW - r} ${y} Q ${x + barW} ${y} ${x + barW} ${y + r} L ${x + barW} ${y + h} Z`,
      fill: cssVar("--s1"), "fill-opacity": 0.78,
    });
    const binLo = lo + (i / nBins) * (hi - lo), binHi = lo + ((i + 1) / nBins) * (hi - lo);
    bar.addEventListener("pointerenter", (evt) => {
      bar.setAttribute("fill-opacity", "1");
      tooltip.style.display = "block";
      tooltip.textContent = "";
      tooltip.appendChild(el("div", { class: "tt-t" }, `[${fmt(binLo, 2)}, ${fmt(binHi, 2)})`));
      const row = el("div", { class: "row" });
      row.appendChild(el("span", {}, "replications"));
      row.appendChild(el("b", {}, `${c} (${fmt((c / vals.length) * 100, 0)}%)`));
      tooltip.appendChild(row);
      tooltip.style.left = Math.min(evt.clientX + 14, innerWidth - 170) + "px";
      tooltip.style.top = (evt.clientY + 12) + "px";
    });
    bar.addEventListener("pointerleave", () => { bar.setAttribute("fill-opacity", "0.78"); tooltip.style.display = "none"; });
    svg.appendChild(bar);
  });
  if (s && s.mean != null && !Number.isNaN(s.mean) && s.mean >= lo && s.mean <= hi) {
    svg.appendChild(svgEl("line", { x1: X(s.mean), x2: X(s.mean), y1: m.t, y2: H - m.b, stroke: cssVar("--s2"), "stroke-width": 2 }));
    svg.appendChild(svgEl("text", { x: X(s.mean), y: m.t - 7, "text-anchor": "middle", fill: cssVar("--ink-2") }, "mean"));
  }
  const p = opts.pcts || {};
  for (const key of ["p10", "p50", "p90"]) {
    const v = p[key];
    if (v == null || Number.isNaN(v) || v < lo || v > hi) continue;
    svg.appendChild(svgEl("line", {
      x1: X(v), x2: X(v), y1: m.t + 8, y2: H - m.b,
      stroke: "var(--axis)", "stroke-width": 1, "stroke-dasharray": "4 3",
    }));
    svg.appendChild(svgEl("text", { x: X(v), y: m.t + 4, "text-anchor": "middle" }, key.toUpperCase()));
  }
  card.appendChild(svg);
}

// Which KPIs deserve a histogram up front: declared outputs (undotted),
// system WIP, and the decision-relevant dotted stats. The rest collapse.
const isPrimaryKpi = (k) =>
  !k.includes(".") || k === "wip.mean" ||
  /\.(time_in_system|wait|elapsed)\.mean$/.test(k) || /\.utilization$/.test(k);

function drawMC(force) {
  if (!$("#panel-mc").classList.contains("active")) { mcDirty = true; return; }
  const root = $("#mc");
  if (!force && !mcDirty && root.childElementCount) return;
  root.textContent = "";
  mcDirty = false;
  if (!MC) {
    const c = el("div", { class: "card" });
    c.textContent = SIM.live
      ? "Set parameters on the Animation tab and run a Monte Carlo (N replications) to see output distributions here."
      : "No replication data embedded in this run.";
    root.appendChild(c);
    return;
  }
  root.appendChild(el("div", { class: "note" },
    `${MC.n} independent replications (${MC.source}). Each histogram is a KPI's distribution across replications — ` +
    `the mean ± CI quantifies the estimate, P10/P50/P90 describe the spread (THEORY.md §5, §8).`));

  const keys = Object.keys(MC.kpi_samples).sort();
  const primary = keys.filter(isPrimaryKpi), rest = keys.filter((k) => !isPrimaryKpi(k));
  const summaryRow = (k) => {
    const s = (MC.kpi_table || {})[k], p = (MC.percentiles || {})[k] || {};
    return [k, ciText(s), fmt(p.p10, 3), fmt(p.p50, 3), fmt(p.p90, 3)];
  };
  root.appendChild(el("h2", { class: "sec" }, "KPI summary"));
  const tcard = el("div", { class: "card" });
  tcard.appendChild(tableOf(["kpi", `mean and ${fmt((MC.confidence ?? 0.95) * 100, 0)}% CI`, "p10", "p50", "p90"],
    [...primary, ...rest].map(summaryRow)));
  root.appendChild(tcard);

  root.appendChild(el("h2", { class: "sec" }, "Output distributions"));
  const grid = el("div", { class: "mc-grid" });
  root.appendChild(grid);
  for (const k of primary)
    histogram(grid, k, MC.kpi_samples[k], { summary: (MC.kpi_table || {})[k], pcts: (MC.percentiles || {})[k] });
  if (rest.length) {
    const det = el("details");
    det.appendChild(el("summary", {}, `All block & pool statistics (${rest.length})`));
    const dgrid = el("div", { class: "mc-grid" });
    det.appendChild(dgrid);
    let rendered = false;
    det.addEventListener("toggle", () => {
      if (!det.open || rendered) return;
      rendered = true;
      for (const k of rest)
        histogram(dgrid, k, MC.kpi_samples[k], { summary: (MC.kpi_table || {})[k], pcts: (MC.percentiles || {})[k] });
    });
    root.appendChild(det);
  }
}

// ---------- report ----------
function tile(lbl, val, sub) {
  const t = el("div", { class: "tile" });
  t.appendChild(el("div", { class: "lbl" }, lbl));
  t.appendChild(el("div", { class: "val" }, val));
  if (sub) t.appendChild(el("div", { class: "sub" }, sub));
  return t;
}
function tableOf(headers, rows, numeric = true) {
  const tb = el("table"); const tr = el("tr");
  headers.forEach((h, i) => tr.appendChild(el("th", { class: numeric && i > 0 ? "num" : "" }, h)));
  tb.appendChild(tr);
  for (const r of rows) {
    const row = el("tr");
    r.forEach((c, i) => {
      const td = el("td", { class: numeric && i > 0 ? "num" : "" });
      if (c instanceof Node) td.appendChild(c); else td.textContent = c;
      row.appendChild(td);
    });
    tb.appendChild(row);
  }
  return tb;
}
function renderReport() {
  const root = $("#report"); root.textContent = "";
  const ent = kpis.entities, run = kpis.run;

  const tiles = el("div", { class: "tiles" });
  tiles.appendChild(tile("Entities completed", fmt(ent.disposed, 0),
    `${fmt(ent.disposed / run.observed_duration, 3)} per ${UNIT.replace(/s$/, "")}`));
  const sinkStats = Object.values(kpis.blocks).find((b) => b.time_in_system);
  if (sinkStats) tiles.appendChild(tile("Mean time in system",
    `${fmt(sinkStats.time_in_system.mean)} ${UNIT}`, `p95 ${fmt(sinkStats.time_in_system.p95)}`));
  tiles.appendChild(tile("Avg entities in system", fmt(ent.wip_mean), `max ${fmt(ent.wip_max, 0)}`));
  for (const [pname, p] of Object.entries(kpis.pools))
    tiles.appendChild(tile(`${pname} utilization`, `${fmt(p.utilization * 100, 1)}%`, `capacity ${p.capacity}`));
  root.appendChild(tiles);

  // Consistency checks.
  root.appendChild(el("h2", { class: "sec" }, "Consistency checks"));
  const chk = el("div", { class: "card" });
  const little = kpis.little;
  const lRow = el("div");
  if (little.residual_rel != null) {
    const ok = little.residual_rel < 0.05;
    lRow.appendChild(el("span", { class: ok ? "ok" : "fail" }, ok ? "✓" : "✗"));
    lRow.appendChild(document.createTextNode(
      ` Little's Law: L = ${fmt(little.L)} vs λ·W = ${fmt(little.lambda * little.W)} ` +
      `(residual ${fmt(little.residual_rel * 100, 2)}%)`));
  } else lRow.textContent = "Little's Law: not computable (no completed entities observed)";
  chk.appendChild(lRow);
  const bal = el("div");
  bal.appendChild(el("span", { class: ent.balance_ok ? "ok" : "fail" }, ent.balance_ok ? "✓" : "✗"));
  bal.appendChild(document.createTextNode(
    ` Entity balance: created ${ent.created} = disposed ${ent.disposed} + dropped ${ent.dropped} + in system ${ent.in_system_at_end}`));
  chk.appendChild(bal);
  root.appendChild(chk);

  // Experiment sections (present when the run came from an experiment).
  if (SIM.experiment) renderExperiment(root, SIM.experiment);

  // Block statistics.
  root.appendChild(el("h2", { class: "sec" }, "Block statistics"));
  const rows = [];
  for (const [name, st] of Object.entries(kpis.blocks)) {
    for (const [k, blob] of Object.entries(st)) {
      if (blob && typeof blob === "object" && "mean" in blob)
        rows.push([`${name} · ${k}`, fmt(blob.mean), fmt(blob.p50 ?? NaN), fmt(blob.p95 ?? NaN), fmt(blob.max)]);
      else if (typeof blob === "number" && blob !== 0)
        rows.push([`${name} · ${k}`, fmt(blob, 0), "–", "–", "–"]);
    }
  }
  const bcard = el("div", { class: "card" });
  bcard.appendChild(tableOf(["statistic", "mean", "p50", "p95", "max"], rows));
  root.appendChild(bcard);

  if (Object.keys(kpis.pools).length) {
    root.appendChild(el("h2", { class: "sec" }, "Resource pools"));
    // Fleets have no queue stat — every blob is optional here.
    const prow = Object.entries(kpis.pools).map(([name, p]) => [
      name, `${fmt(p.utilization * 100, 1)}%`, fmt(p.busy && p.busy.mean),
      fmt(p.queue && p.queue.mean), fmt(p.wait && p.wait.mean), String(p.capacity),
    ]);
    const pcard = el("div", { class: "card" });
    pcard.appendChild(tableOf(["pool", "utilization", "avg busy", "avg queue", "avg wait", "capacity"], prow));
    root.appendChild(pcard);
  }
}
function ciText(s) {
  return s && s.ci_low != null && !Number.isNaN(s.ci_low)
    ? `${fmt(s.mean)} ± ${fmt(s.halfwidth)} [${fmt(s.ci_low)}, ${fmt(s.ci_high)}]` : fmt(s && s.mean);
}
function renderExperiment(root, ex) {
  root.appendChild(el("h2", { class: "sec" },
    `Experiment — ${ex.kind}${ex.n_replications ? ` (${ex.n_replications} replications)` : ""}`));
  if (ex.theory_check) {
    const c = el("div", { class: "card" });
    c.appendChild(el("h3", {}, `Analytic reference: ${ex.theory_check.reference}`));
    const rows = ex.theory_check.metrics.map((m) => [
      m.metric, fmt(m.analytic, 3), `[${fmt(m.ci_low, 3)}, ${fmt(m.ci_high, 3)}]`,
      el("span", { class: m.covered ? "ok" : "fail" }, m.covered ? "✓ covered" : "✗ missed"),
    ]);
    c.appendChild(tableOf(["metric", "analytic", "simulated 95% CI", "check"], rows));
    c.appendChild(el("div", { class: "note" }, ex.theory_check.note));
    root.appendChild(c);
  }
  if (ex.kpi_table) {
    const c = el("div", { class: "card" });
    c.appendChild(el("h3", {}, "KPIs across replications (mean ± CI half-width)"));
    const rows = Object.entries(ex.kpi_table)
      .filter(([, s]) => s.n > 1 && s.mean != null)
      .map(([k, s]) => [k, ciText(s), fmt(s.rel_precision != null ? s.rel_precision * 100 : NaN, 1) + "%"]);
    c.appendChild(tableOf(["kpi", "mean and 95% CI", "rel. precision"], rows));
    root.appendChild(c);
  }
  if (ex.scenarios) {
    const c = el("div", { class: "card" });
    c.appendChild(el("h3", {}, `Scenario comparison — ${ex.scenarios.kpi}`));
    const rows = ex.scenarios.table.map((r) => [JSON.stringify(r.scenario), ciText(r)]);
    c.appendChild(tableOf(["scenario", "mean and 95% CI"], rows));
    if (ex.scenarios.compare && ex.scenarios.compare.length) {
      c.appendChild(el("h3", { style: "margin-top:12px" }, "Differences vs baseline"));
      const drows = ex.scenarios.compare.map((r) => [
        JSON.stringify(r.scenario),
        `${fmt(r.diff_mean)} [${fmt(r.ci_low)}, ${fmt(r.ci_high)}]`,
        el("span", { class: r.distinguishable ? "ok" : "" },
          r.distinguishable ? "distinguishable" : "cannot distinguish"),
      ]);
      c.appendChild(tableOf(["scenario", "Δ vs baseline (95% CI)", "verdict"], drows));
    }
    root.appendChild(c);
  }
  if (ex.sequential) {
    root.appendChild(el("div", { class: "note" },
      `Sequential replication policy on ${ex.sequential.kpi}: target ${fmt(ex.sequential.target_precision * 100, 1)}% ` +
      `relative half-width, achieved ${fmt(ex.sequential.achieved_precision * 100, 1)}% ` +
      `after ${ex.sequential.n_run} replications${ex.sequential.converged ? "" : " (NOT converged)"}.`));
  }
}

// ---------- model tab ----------
// Minimal hand-rolled markdown: the conceptual model is local, trusted-ish
// content, but everything is HTML-escaped before any markup is applied.
function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function mdInline(s) {
  return s
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/\*([^*]+)\*/g, "<i>$1</i>")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2">$1</a>');
}
function mdToHtml(md) {
  md = escapeHtml(md.replace(/\r\n/g, "\n"));
  md = md.replace(/&lt;!--[\s\S]*?--&gt;/g, ""); // comments (escaped form)
  const out = [];
  let inCode = false, listTag = null, para = [], tableRows = null;
  const flushPara = () => { if (para.length) { out.push("<p>" + mdInline(para.join(" ")) + "</p>"); para = []; } };
  const flushList = () => { if (listTag) { out.push("</" + listTag + ">"); listTag = null; } };
  const flushTable = () => {
    if (!tableRows) return;
    let html = "<table>";
    tableRows.forEach((cells, i) => {
      const tag = i === 0 ? "th" : "td";
      html += "<tr>" + cells.map((c) => `<${tag}>${mdInline(c)}</${tag}>`).join("") + "</tr>";
    });
    out.push(html + "</table>");
    tableRows = null;
  };
  for (const raw of md.split("\n")) {
    if (raw.trim().startsWith("```")) {
      flushPara(); flushList(); flushTable();
      out.push(inCode ? "</code></pre>" : "<pre><code>");
      inCode = !inCode;
      continue;
    }
    if (inCode) { out.push(raw); continue; }
    const t = raw.trim();
    if (t.startsWith("|") && t.endsWith("|") && t.length > 1) {
      flushPara(); flushList();
      if (/^[\s:\-|]+$/.test(t)) continue; // header separator row
      (tableRows || (tableRows = [])).push(t.slice(1, -1).split("|").map((c) => c.trim()));
      continue;
    }
    flushTable();
    const h = t.match(/^(#{1,6})\s+(.*)$/);
    if (h) { flushPara(); flushList(); out.push(`<h${h[1].length}>${mdInline(h[2])}</h${h[1].length}>`); continue; }
    if (/^(-{3,}|\*{3,})$/.test(t)) { flushPara(); flushList(); out.push("<hr>"); continue; }
    const li = t.match(/^[-*]\s+(.*)$/) || t.match(/^\d+[.)]\s+(.*)$/);
    if (li) {
      flushPara();
      const want = /^\d/.test(t) ? "ol" : "ul";
      if (listTag !== want) { flushList(); out.push("<" + want + ">"); listTag = want; }
      out.push("<li>" + mdInline(li[1]) + "</li>");
      continue;
    }
    if (t === "") { flushPara(); flushList(); continue; }
    para.push(t);
  }
  flushPara(); flushList(); flushTable();
  if (inCode) out.push("</code></pre>");
  return out.join("\n");
}

// Human-readable distribution form. Accepts both the flat describe() shape
// ({type, mean, sd}), the nested to_dict shape ({type, args:{...}}), and the
// legacy leaked-underscore keys from pre-serialization model.json files.
function prettyDist(d) {
  if (d == null || typeof d !== "object") return typeof d === "number" ? fmt(d, 3) : String(d);
  const a = d.args || d;
  const n = (v) => fmt(v, 3);
  switch (d.type) {
    case "Constant": return n(a.value);
    case "Uniform": return `Uniform(${n(a.low)}, ${n(a.high)})`;
    case "Exponential": return `Exponential(mean=${n(a.mean ?? a._mean)})`;
    case "Triangular": return `Triangular(${n(a.low)}, ${n(a.mode)}, ${n(a.high)})`;
    case "Normal": return `Normal(mean=${n(a.mean ?? a._mean)}, sd=${n(a.sd)})`;
    case "Lognormal": return `Lognormal(mean=${n(a.mean ?? a._mean)}, sd=${n(a.sd)})`;
    case "Gamma": return `Gamma(shape=${n(a.shape)}, scale=${n(a.scale)})`;
    case "Erlang": return `Erlang(k=${a.k}, mean=${n(a.mean ?? a.shape * a.scale)})`;
    case "Weibull": return `Weibull(shape=${n(a.shape)}, scale=${n(a.scale)})`;
    case "Pert":
      return `Pert(${n(a.low)}, ${n(a.mode)}, ${n(a.high)}${a.lam != null && a.lam !== 4 ? `, λ=${n(a.lam)}` : ""})`;
    case "Empirical": {
      const count = a.n ?? (a.data ? a.data.length : null);
      const mean = a.mean ?? (a.data ? a.data.reduce((s, x) => s + x, 0) / a.data.length : null);
      return `Empirical(n=${count}, mean≈${n(mean)})`;
    }
    case "Choice": {
      const probs = a.probs || a.weights || [];
      return "Choice(" + (a.values || []).map((v, i) => `${n(v)}: ${fmt((probs[i] ?? 0) * 100, 0)}%`).join(", ") + ")";
    }
    case "RateSchedule": {
      const bps = (a.breakpoints || []).map(([t, r]) => `${fmt(t, 0)}→${fmt(r, 3)}`).join(", ");
      return `rate schedule: ${bps}` + (a.cycle ? ` (cycles every ${fmt(a.cycle, 0)})` : "");
    }
    case "expression": return `fn ⟨${a.name || "?"}⟩`;
    default: {
      const parts = Object.entries(a)
        .filter(([k]) => k !== "type" && !k.startsWith("_"))
        .map(([k, v]) => `${k}=${typeof v === "number" ? n(v) : JSON.stringify(v)}`);
      return `${d.type || "?"}(${parts.join(", ")})`;
    }
  }
}
function prettyParams(params) {
  const parts = [];
  for (const [k, v] of Object.entries(params || {})) {
    if (v == null) continue;
    if (Array.isArray(v)) parts.push(`${k}: [${v.map((x) => (typeof x === "number" ? fmt(x, 3) : x)).join(", ")}]`);
    else if (typeof v === "object") parts.push(`${k}: ${prettyDist(v)}`);
    else if (typeof v === "number") parts.push(`${k}: ${fmt(v, 3)}`);
    else parts.push(`${k}: ${v}`);
  }
  return parts.join(" · ");
}

function renderModel() {
  const doc = $("#doc");
  if (SIM.conceptual_model) { doc.innerHTML = mdToHtml(SIM.conceptual_model); doc.hidden = false; }
  else doc.hidden = true;

  const root = $("#datadef");
  root.textContent = "";

  if (SIM.factors && SIM.factors.length) {
    root.appendChild(el("h2", { class: "sec" }, "Experimental factors"));
    const rows = SIM.factors.map((f) => [
      f.label || f.name,
      f.kind,
      f.kind === "distribution" || f.kind === "schedule" ? prettyDist(f.default) : String(f.default),
      f.options ? f.options.join(", ")
        : (f.min != null || f.max != null)
          ? `${f.min ?? "…"} – ${f.max ?? "…"}${f.step ? ` (step ${f.step})` : ""}` : "–",
    ]);
    const c = el("div", { class: "card" });
    c.appendChild(tableOf(["factor", "kind", "default", "range / options"], rows, false));
    c.appendChild(el("div", { class: "note" },
      "Factors are the model's declared knobs — the keyword arguments of make_model(). Everything below is fixed in the model definition."));
    root.appendChild(c);
  }

  root.appendChild(el("h2", { class: "sec" }, "Blocks"));
  const bc = el("div", { class: "card" });
  bc.appendChild(tableOf(
    ["block", "type", "parameters"],
    model.blocks.map((b) => [b.name, b.type, prettyParams(b.params) || "–"]),
    false,
  ));
  root.appendChild(bc);

  const frows = [];
  for (const b of model.blocks)
    for (const [port, tgt] of Object.entries(b.outputs || {}))
      if (tgt) frows.push([b.name, port, tgt]);
  if (frows.length) {
    root.appendChild(el("h2", { class: "sec" }, "Flow"));
    const fc = el("div", { class: "card" });
    fc.appendChild(tableOf(["from", "port", "to"], frows, false));
    root.appendChild(fc);
  }

  if (model.pools && model.pools.length) {
    root.appendChild(el("h2", { class: "sec" }, "Resource pools"));
    const pc = el("div", { class: "card" });
    pc.appendChild(tableOf(
      ["pool", "capacity", "details"],
      model.pools.map((p) => [
        p.name,
        String(p.capacity),
        Object.entries(p)
          .filter(([k, v]) => !["name", "capacity"].includes(k) && v != null)
          .map(([k, v]) => `${k}: ${typeof v === "object" ? prettyDist(v) : typeof v === "number" ? fmt(v, 3) : v}`)
          .join(" · ") || "–",
      ]),
      false,
    ));
    root.appendChild(pc);
  }
}

// ---------- parameters & live mode ----------
// Editable distribution types and their ordered args (mirrors
// factors.distribution_catalog on the Python side).
const DIST_PARAMS = {
  Constant: ["value"], Uniform: ["low", "high"], Exponential: ["mean"],
  Triangular: ["low", "mode", "high"], Normal: ["mean", "sd"], Lognormal: ["mean", "sd"],
  Gamma: ["shape", "scale"], Erlang: ["k", "mean"], Weibull: ["shape", "scale"],
  Pert: ["low", "mode", "high", "lam"],
};
// Normalize a distribution spec ({type, args} or flat, incl. legacy _mean).
function distArgsOf(spec) {
  const a = (spec && (spec.args || spec)) || {};
  const out = {};
  for (const k of DIST_PARAMS[spec && spec.type] || [])
    out[k] = a[k] ?? (k === "mean" ? a._mean : undefined) ?? "";
  return out;
}

let inflight = false;
function setBusy(on) {
  inflight = on;
  $("#runBtn").disabled = on || !SIM.live;
  $("#runMcBtn").disabled = on || !SIM.live;
  $("#busy").hidden = !on;
}
function showError(msg) { $("#errmsg").textContent = msg; $("#errbar").hidden = false; }
$("#errclose").addEventListener("click", () => { $("#errbar").hidden = true; });

// The only network calls in the file; unreachable in static mode.
async function api(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let msg = null;
    try { msg = (await r.json()).error; } catch (e) { /* non-JSON error body */ }
    throw new Error(msg || `${r.status} ${r.statusText}`);
  }
  return r.json();
}

function distField(f) {
  const wrap = el("div", { "data-factor-wrap": f.name });
  const field = el("div", { class: "field" });
  field.appendChild(el("label", {}, f.label || f.name));
  const sel = el("select", { "data-factor": f.name });
  const defType = f.default && f.default.type;
  for (const t of Object.keys(DIST_PARAMS)) {
    const o = el("option", { value: t }, t);
    if (t === defType) o.selected = true;
    sel.appendChild(o);
  }
  // A default outside the editable catalog (Choice, Empirical…) stays view-only.
  if (defType && !DIST_PARAMS[defType]) {
    const note = el("div", { class: "note" }, `${prettyDist(f.default)} (not editable)`);
    wrap.appendChild(field); field.appendChild(el("span", {}, ""));
    wrap.appendChild(note);
    sel.remove();
    return wrap;
  }
  field.appendChild(sel);
  wrap.appendChild(field);
  const argsDiv = el("div", { class: "dist-params" });
  wrap.appendChild(argsDiv);
  const rebuild = () => {
    const prev = {};
    argsDiv.querySelectorAll("input[data-arg]").forEach((i) => { prev[i.dataset.arg] = i.value; });
    argsDiv.textContent = "";
    const seed = sel.value === defType ? distArgsOf(f.default) : {};
    for (const arg of DIST_PARAMS[sel.value]) {
      const row = el("div", { class: "field" });
      row.appendChild(el("label", {}, arg));
      const inp = el("input", { type: "number", step: "any", "data-arg": arg });
      inp.value = prev[arg] ?? seed[arg] ?? "";
      row.appendChild(inp);
      argsDiv.appendChild(row);
    }
  };
  sel.addEventListener("change", rebuild);
  rebuild();
  return wrap;
}

function buildParamPanel() {
  const panel = $("#params");
  const show = SIM.live || (SIM.factors && SIM.factors.length);
  panel.hidden = !show;
  if (!show) return;
  const root = $("#factorFields");
  root.textContent = "";
  for (const f of SIM.factors || []) {
    if (f.kind === "distribution") { root.appendChild(distField(f)); continue; }
    const field = el("div", { class: "field" });
    field.appendChild(el("label", {}, f.label || f.name));
    if (f.kind === "fixed" || f.kind === "schedule") {
      field.appendChild(el("span", { class: "note" },
        f.kind === "schedule" ? prettyDist(f.default) : String(f.default)));
    } else if (f.kind === "bool") {
      const inp = el("input", { type: "checkbox", "data-factor": f.name });
      inp.checked = !!f.default;
      field.appendChild(inp);
    } else if (f.kind === "choice") {
      const sel = el("select", { "data-factor": f.name });
      for (const o of f.options) {
        const opt = el("option", { value: String(o) }, String(o));
        if (o === f.default) opt.selected = true;
        sel.appendChild(opt);
      }
      field.appendChild(sel);
    } else if (f.kind === "str") {
      const inp = el("input", { type: "text", "data-factor": f.name });
      inp.value = f.default;
      field.appendChild(inp);
    } else {
      const attrs = { type: "number", "data-factor": f.name, step: String(f.step ?? (f.kind === "int" ? 1 : "any")) };
      if (f.min != null) attrs.min = String(f.min);
      if (f.max != null) attrs.max = String(f.max);
      const inp = el("input", attrs);
      inp.value = f.default;
      field.appendChild(inp);
    }
    root.appendChild(field);
  }
  $("#seedInput").value = kpis.run.seed;
  if (!SIM.live) {
    $("#staticHint").hidden = false;
    panel.querySelectorAll("input, select, button").forEach((e) => { e.disabled = true; });
  }
}

function readFactors() {
  const out = {};
  for (const f of SIM.factors || []) {
    if (f.kind === "fixed" || f.kind === "schedule") continue;
    const ctl = document.querySelector(`[data-factor="${f.name}"]`);
    if (!ctl) continue;
    if (f.kind === "bool") { out[f.name] = ctl.checked; continue; }
    if (f.kind === "choice") { out[f.name] = f.options[ctl.selectedIndex]; continue; }
    if (f.kind === "str") { out[f.name] = ctl.value; continue; }
    if (f.kind === "distribution") {
      const wrap = document.querySelector(`[data-factor-wrap="${f.name}"]`);
      if (!wrap || !wrap.querySelector("select")) continue; // view-only default
      const args = {};
      wrap.querySelectorAll("input[data-arg]").forEach((i) => {
        const v = parseFloat(i.value);
        if (Number.isNaN(v)) throw new Error(`${f.label || f.name}: fill in "${i.dataset.arg}"`);
        args[i.dataset.arg] = v;
      });
      out[f.name] = { type: ctl.value, args };
      continue;
    }
    const v = f.kind === "int" ? parseInt(ctl.value, 10) : parseFloat(ctl.value);
    if (Number.isNaN(v)) throw new Error(`${f.label || f.name}: enter a number`);
    out[f.name] = v;
  }
  return out;
}

async function runOnce() {
  if (!SIM.live || inflight) return;
  try {
    setBusy(true);
    $("#errbar").hidden = true;
    const seed = parseInt($("#seedInput").value, 10);
    const resp = await api("/api/run", { factors: readFactors(), seed });
    reinit(resp);
  } catch (e) { showError(e.message); }
  finally { setBusy(false); }
}
async function runMC() {
  if (!SIM.live || inflight) return;
  try {
    setBusy(true);
    $("#errbar").hidden = true;
    const n = parseInt($("#mcN").value, 10);
    const seed = parseInt($("#seedInput").value, 10);
    const resp = await api("/api/replicate", { factors: readFactors(), n, seed });
    MC = {
      n: resp.n, confidence: resp.confidence, kpi_table: resp.kpi_table,
      kpi_samples: resp.kpi_samples, percentiles: resp.percentiles, source: "live run",
    };
    $("#mcTabBtn").hidden = false;
    mcDirty = true;
    document.querySelector('[data-tab="mc"]').click();
  } catch (e) { showError(e.message); }
  finally { setBusy(false); }
}
$("#runBtn").addEventListener("click", runOnce);
$("#runMcBtn").addEventListener("click", runMC);

// ---------- boot / reinit ----------
// reinit() swaps in a whole run ({model, trace, kpis}) — used at boot with
// the embedded SIM and by the live parameter panel after POST /api/run.
function reinit(payload) {
  SIM.model = payload.model; SIM.trace = payload.trace; SIM.kpis = payload.kpis;
  model = SIM.model; kpis = SIM.kpis; T_END = kpis.run.t_end; UNIT = model.time_unit;
  deriveState();
  computeLayout();
  sizeCanvas();
  renderHeader();
  setPlaying(false);
  simT = 0;
  draw();
  renderReport();
  renderModel();
  if ($("#panel-charts").classList.contains("active")) drawCharts();
}
reinit(SIM);
seedMC();
buildParamPanel();
setBusy(false);
requestAnimationFrame(tick);
// Headless/E2E hook: http://…/?autorun=1 runs once with default factors.
if (SIM.live && new URLSearchParams(location.search).has("autorun")) runOnce();

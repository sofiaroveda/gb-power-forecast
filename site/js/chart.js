// Small SVG charts with a hover tooltip. No libraries: each chart is drawn from
// plain numbers, and redrawn when the window is resized.

const NS = "http://www.w3.org/2000/svg";

function el(tag, attrs = {}, parent) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

// Round axis steps: 1, 2, 5, 10, 20, 50 ...
function niceTicks(min, max, count = 5) {
  if (min === max) { min -= 1; max += 1; }
  const raw = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw);
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Math.round(v * 1e6) / 1e6);
  return ticks;
}

export function legend(container, series) {
  const box = document.createElement("div");
  box.className = "legend";
  for (const s of series) {
    const item = document.createElement("span");
    item.className = "legend-item";
    item.innerHTML = `<span class="swatch${s.dashed ? " dashed" : ""}" style="--c: var(${s.color})"></span>${s.name}`;
    box.appendChild(item);
  }
  container.appendChild(box);
}

function tooltip(wrap) {
  const tip = document.createElement("div");
  tip.className = "tooltip";
  tip.hidden = true;
  wrap.appendChild(tip);
  return tip;
}

function placeTip(tip, wrap, x, y) {
  tip.hidden = false;
  const w = tip.offsetWidth;
  const left = x + 14 + w > wrap.clientWidth ? x - 14 - w : x + 14;
  tip.style.left = `${Math.max(0, left)}px`;
  tip.style.top = `${Math.max(0, y - 10)}px`;
}

function draw(container, render) {
  const go = () => { container.innerHTML = ""; render(container.clientWidth); };
  go();
  let last = container.clientWidth;
  new ResizeObserver(() => {
    if (Math.abs(container.clientWidth - last) > 4) { last = container.clientWidth; go(); }
  }).observe(container);
}

// opts: labels (tooltip title per point), series [{name, values, color (CSS var name),
// dashed, width}], xTicks [{i, label}], height, format (value -> text)
export function lineChart(container, opts) {
  const { labels, series, xTicks = [], height = 300, format = (v) => v.toFixed(0) } = opts;
  if (opts.legend !== false) legend(container.parentElement.querySelector(".legend-slot") || container, series);
  draw(container, (width) => {
    const m = { l: 46, r: 12, t: 10, b: 26 };
    const n = labels.length;
    const vals = series.flatMap((s) => s.values).filter((v) => v != null && Number.isFinite(v));
    const ticks = niceTicks(Math.min(...vals, opts.includeZero ? 0 : Infinity), Math.max(...vals));
    const y0 = ticks[0], y1 = ticks[ticks.length - 1];
    const x = (i) => m.l + (n === 1 ? 0 : (i / (n - 1)) * (width - m.l - m.r));
    const y = (v) => m.t + (1 - (v - y0) / (y1 - y0)) * (height - m.t - m.b);

    const wrap = document.createElement("div");
    wrap.className = "chart-wrap";
    container.appendChild(wrap);
    const svg = el("svg", { width, height, viewBox: `0 0 ${width} ${height}`, role: "img",
      "aria-label": opts.title || "" }, wrap);

    for (const t of ticks) {
      el("line", { x1: m.l, x2: width - m.r, y1: y(t), y2: y(t),
        class: t === 0 && y0 < 0 ? "axis" : "grid" }, svg);
      el("text", { x: m.l - 8, y: y(t) + 4, class: "tick", "text-anchor": "end" }, svg).textContent = format(t);
    }
    el("line", { x1: m.l, x2: width - m.r, y1: height - m.b, y2: height - m.b, class: "axis" }, svg);
    let lastRight = -Infinity;
    for (const t of xTicks) {
      const tx = x(t.i);
      const half = t.label.length * 3.6; // about half the label's width at 12px
      if (tx - half < lastRight + 8) continue; // skip labels that would overlap
      lastRight = tx + half;
      el("line", { x1: tx, x2: tx, y1: height - m.b, y2: height - m.b + 4, class: "axis" }, svg);
      el("text", { x: tx, y: height - 8, class: "tick", "text-anchor": "middle" }, svg).textContent = t.label;
    }

    for (const s of series) {
      let d = "", pen = false;
      s.values.forEach((v, i) => {
        if (v == null || !Number.isFinite(v)) { pen = false; return; }
        d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
        pen = true;
      });
      el("path", { d, fill: "none", stroke: `var(${s.color})`, "stroke-width": s.width || 2,
        "stroke-linejoin": "round", "stroke-linecap": "round",
        "stroke-dasharray": s.dashed ? "5 4" : "none" }, svg);
    }

    // hover: crosshair, a dot on each line and a tooltip with every value
    const cross = el("line", { y1: m.t, y2: height - m.b, class: "crosshair", visibility: "hidden" }, svg);
    const dots = series.map((s) => el("circle", { r: 4, fill: `var(${s.color})`, class: "dot",
      visibility: "hidden" }, svg));
    const tip = tooltip(wrap);
    const hit = el("rect", { x: m.l, y: 0, width: width - m.l - m.r, height, fill: "transparent" }, svg);
    const show = (evt) => {
      const r = svg.getBoundingClientRect();
      const px = evt.clientX - r.left;
      const i = Math.max(0, Math.min(n - 1, Math.round(((px - m.l) / (width - m.l - m.r)) * (n - 1))));
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i));
      cross.setAttribute("visibility", "visible");
      let rows = "";
      series.forEach((s, k) => {
        const v = s.values[i];
        const ok = v != null && Number.isFinite(v);
        dots[k].setAttribute("visibility", ok ? "visible" : "hidden");
        if (ok) { dots[k].setAttribute("cx", x(i)); dots[k].setAttribute("cy", y(v)); }
        rows += `<div class="tip-row"><span class="swatch${s.dashed ? " dashed" : ""}" style="--c: var(${s.color})"></span>${s.name}<b>${ok ? format(v) : "–"}</b></div>`;
      });
      tip.innerHTML = `<div class="tip-title">${labels[i]}</div>${rows}`;
      placeTip(tip, wrap, x(i), evt.clientY - r.top);
    };
    const hide = () => {
      tip.hidden = true;
      cross.setAttribute("visibility", "hidden");
      dots.forEach((dt) => dt.setAttribute("visibility", "hidden"));
    };
    hit.addEventListener("pointermove", show);
    hit.addEventListener("pointerdown", show);
    hit.addEventListener("pointerleave", hide);
  });
}

// Grouped columns. opts: groups (labels), series [{name, values, color}], height, format
export function columnChart(container, opts) {
  const { groups, series, height = 260, format = (v) => v.toFixed(1) } = opts;
  legend(container.parentElement.querySelector(".legend-slot") || container, series);
  draw(container, (width) => {
    const m = { l: 46, r: 8, t: 10, b: 26 };
    const vals = series.flatMap((s) => s.values).filter(Number.isFinite);
    const ticks = niceTicks(0, Math.max(...vals), 4);
    const top = ticks[ticks.length - 1];
    const y = (v) => m.t + (1 - v / top) * (height - m.t - m.b);
    const band = (width - m.l - m.r) / groups.length;
    const bar = Math.min(24, Math.max(3, (band * 0.75 - 2 * (series.length - 1)) / series.length));
    const groupW = bar * series.length + 2 * (series.length - 1);

    const wrap = document.createElement("div");
    wrap.className = "chart-wrap";
    container.appendChild(wrap);
    const svg = el("svg", { width, height, viewBox: `0 0 ${width} ${height}`, role: "img",
      "aria-label": opts.title || "" }, wrap);
    for (const t of ticks) {
      el("line", { x1: m.l, x2: width - m.r, y1: y(t), y2: y(t), class: t === 0 ? "axis" : "grid" }, svg);
      el("text", { x: m.l - 8, y: y(t) + 4, class: "tick", "text-anchor": "end" }, svg).textContent = format(t);
    }
    const tip = tooltip(wrap);
    const every = Math.ceil(44 / band);
    groups.forEach((g, gi) => {
      const gx = m.l + gi * band + (band - groupW) / 2;
      if (gi % every === 0) {
        el("text", { x: m.l + gi * band + band / 2, y: height - 8, class: "tick", "text-anchor": "middle" }, svg)
          .textContent = opts.short ? opts.short(g) : g;
      }
      series.forEach((s, si) => {
        const v = s.values[gi];
        const bx = gx + si * (bar + 2), by = y(v), bh = y(0) - by;
        const r = Math.min(4, bar / 2, bh);
        // rounded top, square at the baseline
        el("path", { d: `M${bx},${y(0)}V${by + r}Q${bx},${by} ${bx + r},${by}H${bx + bar - r}Q${bx + bar},${by} ${bx + bar},${by + r}V${y(0)}Z`,
          fill: `var(${s.color})` }, svg);
      });
      const hit = el("rect", { x: m.l + gi * band, y: m.t, width: band, height: height - m.t - m.b, fill: "transparent" }, svg);
      const show = (evt) => {
        const r = svg.getBoundingClientRect();
        tip.innerHTML = `<div class="tip-title">${g}</div>` + series.map((s) =>
          `<div class="tip-row"><span class="swatch" style="--c: var(${s.color})"></span>${s.name}<b>${format(s.values[gi])}</b></div>`).join("");
        placeTip(tip, wrap, m.l + gi * band + band / 2, evt.clientY - r.top);
      };
      hit.addEventListener("pointermove", show);
      hit.addEventListener("pointerdown", show);
      hit.addEventListener("pointerleave", () => { tip.hidden = true; });
    });
  });
}

/* Small SVG chart set for the SAA tool.
   Written by hand instead of pulling in a chart library so the tool runs with
   no network access at all: one Python process, no CDN, no npm.

   Conventions follow one house style throughout: thin marks, hairline grid,
   a legend whenever two or more series share a plot, selective direct labels
   at the line ends, and a hover layer on every plot. */

const NS = "http://www.w3.org/2000/svg";

export const SERIES = ["--series-1", "--series-2", "--series-3", "--series-4", "--series-5", "--series-6"];
export const seriesColor = (i) => `var(${SERIES[i % SERIES.length]})`;

/* ---------------------------------------------------------------- helpers -- */
function el(name, attrs = {}, parent = null) {
  const node = document.createElementNS(NS, name);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined) continue;
    node.setAttribute(key, String(value));
  }
  if (parent) parent.appendChild(node);
  return node;
}

export const truncate = (text, max) =>
  text && text.length > max ? `${text.slice(0, max - 1)}…` : text || "";

export const fmt = {
  pct: (v, d = 2) => (v === null || v === undefined || Number.isNaN(v) ? "–" : `${(v * 100).toFixed(d)} %`),
  pctSigned: (v, d = 2) =>
    v === null || v === undefined || Number.isNaN(v) ? "–" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(d)} %`,
  num: (v, d = 2) => (v === null || v === undefined || Number.isNaN(v) ? "–" : v.toFixed(d)),
  idx: (v) => (v === null || v === undefined || Number.isNaN(v) ? "–" : v.toFixed(1)),
  month: (m) => (m ? m : "–"),
};

/* Axis ticks: round numbers inside [lo, hi], at most `count` of them. */
export function niceTicks(lo, hi, count = 5) {
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [0];
  if (hi === lo) return [lo];
  const raw = (hi - lo) / Math.max(count, 2);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const stepFactor = norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1;
  const step = stepFactor * mag;
  const out = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + step * 1e-9; t += step) {
    out.push(Math.abs(t) < step * 1e-9 ? 0 : t);
  }
  return out.length ? out : [lo, hi];
}

/* One shared tooltip element, positioned in viewport coordinates. */
let tipNode = null;
function tip() {
  if (!tipNode) {
    tipNode = document.createElement("div");
    tipNode.className = "tooltip";
    tipNode.setAttribute("role", "status");
    document.body.appendChild(tipNode);
  }
  return tipNode;
}
export function showTip(html, event) {
  const node = tip();
  node.innerHTML = html;
  node.classList.add("show");
  const box = node.getBoundingClientRect();
  let x = event.clientX + 14;
  let y = event.clientY + 14;
  if (x + box.width > window.innerWidth - 8) x = event.clientX - box.width - 14;
  if (y + box.height > window.innerHeight - 8) y = event.clientY - box.height - 14;
  node.style.left = `${Math.max(8, x)}px`;
  node.style.top = `${Math.max(8, y)}px`;
}
export function hideTip() {
  if (tipNode) tipNode.classList.remove("show");
}

function tipRows(rows) {
  return rows
    .map(
      (r) =>
        `<div class="t-row"><span class="k">${
          r.color ? `<span class="key" style="background:${r.color}"></span>` : ""
        }${r.label}</span><span class="v">${r.value}</span></div>`
    )
    .join("");
}

/* A plot frame: svg + inner group, grid, axes, and a hover capture rect. */
function frame(host, { width = 860, height = 320, pad = {} } = {}) {
  const margin = { top: 14, right: 118, bottom: 30, left: 56, ...pad };
  host.innerHTML = "";
  const svg = el("svg", {
    viewBox: `0 0 ${width} ${height}`,
    preserveAspectRatio: "xMidYMid meet",
    role: "img",
  }, host);
  const plot = {
    svg,
    margin,
    width,
    height,
    w: width - margin.left - margin.right,
    h: height - margin.top - margin.bottom,
  };
  plot.g = el("g", { transform: `translate(${margin.left},${margin.top})` }, svg);
  return plot;
}

function yAxis(plot, scale, ticks, format, title) {
  const grid = el("g", { class: "grid" }, plot.g);
  const axis = el("g", { class: "axis" }, plot.g);
  for (const t of ticks) {
    const y = scale(t);
    if (!Number.isFinite(y)) continue;
    el("line", { x1: 0, x2: plot.w, y1: y, y2: y }, grid);
    const label = el("text", { x: -8, y, "text-anchor": "end", "dominant-baseline": "middle" }, axis);
    label.textContent = format(t);
  }
  el("line", { x1: 0, x2: 0, y1: 0, y2: plot.h }, axis);
  if (title) {
    const t = el("text", {
      class: "axis-title",
      transform: `translate(${-plot.margin.left + 12},${plot.h / 2}) rotate(-90)`,
      "text-anchor": "middle",
    }, plot.g);
    t.textContent = title;
  }
}

function xAxisBand(plot, labels, positions) {
  const axis = el("g", { class: "axis", transform: `translate(0,${plot.h})` }, plot.g);
  el("line", { x1: 0, x2: plot.w, y1: 0, y2: 0 }, axis);
  labels.forEach((label, i) => {
    const t = el("text", { x: positions[i], y: 16, "text-anchor": "middle" }, axis);
    t.textContent = label;
  });
}

/* Pick ~`count` evenly spaced indices for x labels. */
function labelIndices(n, count = 7) {
  if (n <= count) return [...Array(n).keys()];
  const out = [];
  for (let i = 0; i < count; i++) out.push(Math.round((i * (n - 1)) / (count - 1)));
  return [...new Set(out)];
}

/* ------------------------------------------------------------- line chart -- */
/* series: [{name, color, values:[number|null]}], months: [label] */
export function lineChart(host, { months, series, yFormat = fmt.idx, yTitle = "", height = 330, logScale = false, zeroLine = false, valueFormat = null }) {
  if (!months?.length || !series?.length) {
    host.innerHTML = `<p class="muted">Keine Daten für diesen Zeitraum.</p>`;
    return;
  }
  const plot = frame(host, { height });
  const flat = series.flatMap((s) => s.values).filter((v) => Number.isFinite(v));
  if (!flat.length) {
    host.innerHTML = `<p class="muted">Keine Daten für diesen Zeitraum.</p>`;
    return;
  }

  const useLog = logScale && flat.every((v) => v > 0);
  let lo = Math.min(...flat);
  let hi = Math.max(...flat);
  if (zeroLine) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
  if (lo === hi) { lo -= Math.abs(lo) * 0.05 + 1e-6; hi += Math.abs(hi) * 0.05 + 1e-6; }
  const padY = (hi - lo) * 0.06;
  lo -= padY; hi += padY;

  const tf = useLog ? Math.log10 : (v) => v;
  const y = (v) => plot.h - ((tf(v) - tf(lo)) / (tf(hi) - tf(lo))) * plot.h;
  const x = (i) => (months.length === 1 ? plot.w / 2 : (i / (months.length - 1)) * plot.w);

  const ticks = useLog
    ? niceTicks(lo, hi, 5)
    : niceTicks(lo, hi, 5);
  yAxis(plot, y, ticks.filter((t) => t >= lo && t <= hi), yFormat, yTitle);

  const idx = labelIndices(months.length, 7);
  xAxisBand(plot, idx.map((i) => months[i]), idx.map((i) => x(i)));

  if (zeroLine && lo < 0 && hi > 0) {
    el("line", { x1: 0, x2: plot.w, y1: y(0), y2: y(0), stroke: "var(--border-strong)", "stroke-width": 1 }, plot.g);
  }

  const endLabels = [];
  series.forEach((s, si) => {
    const color = s.color || seriesColor(si);
    let path = "";
    let open = false;
    s.values.forEach((v, i) => {
      if (!Number.isFinite(v)) { open = false; return; }
      path += `${open ? "L" : "M"}${x(i).toFixed(2)},${y(v).toFixed(2)}`;
      open = true;
    });
    if (s.fillToZero) {
      const base = y(Math.max(lo, Math.min(hi, 0)));
      const first = s.values.findIndex((v) => Number.isFinite(v));
      let last = -1;
      s.values.forEach((v, i) => { if (Number.isFinite(v)) last = i; });
      if (first >= 0 && last > first) {
        el("path", {
          d: `${path}L${x(last).toFixed(2)},${base.toFixed(2)}L${x(first).toFixed(2)},${base.toFixed(2)}Z`,
          fill: color, "fill-opacity": 0.1, stroke: "none",
        }, plot.g);
      }
    }
    el("path", { d: path, class: "series-line", stroke: color }, plot.g);

    // Selective direct label: the series end, which also covers the
    // light-mode contrast relief rule (identity never rests on colour alone).
    let lastIdx = -1;
    s.values.forEach((v, i) => { if (Number.isFinite(v)) lastIdx = i; });
    if (lastIdx >= 0) {
      endLabels.push({
        x: x(lastIdx) + 7,
        y: y(s.values[lastIdx]),
        color,
        text: truncate(s.shortName || s.name, 13),
      });
    }
  });

  // Nudge end labels apart so two close series do not print on top of each other.
  endLabels.sort((a, b) => a.y - b.y);
  const minGap = 13;
  for (let i = 1; i < endLabels.length; i++) {
    if (endLabels[i].y - endLabels[i - 1].y < minGap) {
      endLabels[i].y = endLabels[i - 1].y + minGap;
    }
  }
  const overshoot = endLabels.length ? endLabels[endLabels.length - 1].y - plot.h : 0;
  if (overshoot > 0) endLabels.forEach((l) => (l.y -= overshoot));
  for (const label of endLabels) {
    const node = el("text", {
      class: "end-label", x: label.x, y: label.y, fill: label.color,
      "dominant-baseline": "middle",
    }, plot.g);
    node.textContent = label.text;
  }

  // Hover: crosshair + one tooltip row per series.
  const hoverLine = el("line", { y1: 0, y2: plot.h, stroke: "var(--border-strong)", "stroke-width": 1, opacity: 0 }, plot.g);
  const dots = series.map((s, si) =>
    el("circle", { r: 4, fill: s.color || seriesColor(si), class: "mark-ring", opacity: 0 }, plot.g)
  );
  const capture = el("rect", { x: 0, y: 0, width: plot.w, height: plot.h, fill: "transparent" }, plot.g);
  const vfmt = valueFormat || yFormat;

  capture.addEventListener("mousemove", (event) => {
    const box = capture.getBoundingClientRect();
    const ratio = (event.clientX - box.left) / box.width;
    const i = Math.max(0, Math.min(months.length - 1, Math.round(ratio * (months.length - 1))));
    hoverLine.setAttribute("x1", x(i));
    hoverLine.setAttribute("x2", x(i));
    hoverLine.setAttribute("opacity", 1);
    const rows = [];
    series.forEach((s, si) => {
      const v = s.values[i];
      if (Number.isFinite(v)) {
        dots[si].setAttribute("cx", x(i));
        dots[si].setAttribute("cy", y(v));
        dots[si].setAttribute("opacity", 1);
        rows.push({ label: s.name, value: vfmt(v), color: s.color || seriesColor(si) });
      } else {
        dots[si].setAttribute("opacity", 0);
      }
    });
    showTip(`<div class="t-title">${months[i]}</div>${tipRows(rows)}`, event);
  });
  capture.addEventListener("mouseleave", () => {
    hoverLine.setAttribute("opacity", 0);
    dots.forEach((d) => d.setAttribute("opacity", 0));
    hideTip();
  });
}

/* -------------------------------------------------------------- bar chart -- */
/* One series of magnitudes. Diverging colour when values cross zero, because
   then the sign is the message; otherwise a single hue. */
export function barChart(host, { labels, values, valueFormat = fmt.pctSigned, height = null, horizontal = true, extra = null, yTitle = "" }) {
  if (!labels?.length) {
    host.innerHTML = `<p class="muted">Keine Daten.</p>`;
    return;
  }
  const finite = values.filter((v) => Number.isFinite(v));
  const hasNegative = finite.some((v) => v < 0);

  if (horizontal) {
    const rowH = 26;
    const plot = frame(host, {
      height: labels.length * rowH + 44,
      pad: { left: 196, right: 78, top: 8, bottom: 30 },
    });
    const lo = Math.min(0, ...finite);
    const hi = Math.max(0, ...finite);
    const span = hi - lo || 1;
    const x = (v) => ((v - lo) / span) * plot.w;

    const ticks = niceTicks(lo, hi, 5);
    const grid = el("g", { class: "grid" }, plot.g);
    const axis = el("g", { class: "axis", transform: `translate(0,${plot.h})` }, plot.g);
    for (const t of ticks) {
      el("line", { x1: x(t), x2: x(t), y1: 0, y2: plot.h }, grid);
      const lab = el("text", { x: x(t), y: 16, "text-anchor": "middle" }, axis);
      lab.textContent = valueFormat(t, 1);
    }
    el("line", { x1: x(0), x2: x(0), y1: 0, y2: plot.h, stroke: "var(--border-strong)", "stroke-width": 1 }, plot.g);

    labels.forEach((label, i) => {
      const v = values[i];
      const yTop = i * rowH + 4;
      const barH = rowH - 10;
      const color = !hasNegative ? "var(--pos)" : v >= 0 ? "var(--pos)" : "var(--neg)";
      const from = Math.min(x(0), x(v));
      const to = Math.max(x(0), x(v));
      const w = Math.max(to - from, 1);

      const rect = el("rect", {
        x: from, y: yTop, width: w, height: barH,
        rx: 4, fill: color, "fill-opacity": 0.92,
      }, plot.g);

      const nameText = el("text", {
        x: -10, y: yTop + barH / 2, "text-anchor": "end", "dominant-baseline": "middle",
        "font-size": 11.5, fill: "var(--text-secondary)",
      }, plot.g);
      nameText.textContent = label;

      // Value sits outside the bar end, so it never gets clipped by a short bar.
      const valText = el("text", {
        x: v >= 0 ? to + 7 : from - 7,
        y: yTop + barH / 2,
        "text-anchor": v >= 0 ? "start" : "end",
        "dominant-baseline": "middle",
        "font-size": 11.5, fill: "var(--text-primary)",
        "font-family": "var(--mono)",
      }, plot.g);
      valText.textContent = valueFormat(v);

      const hit = el("rect", { x: 0, y: i * rowH, width: plot.w, height: rowH, fill: "transparent" }, plot.g);
      const detail = extra ? extra(i) : [];
      hit.addEventListener("mousemove", (e) =>
        showTip(`<div class="t-title">${label}</div>${tipRows([{ label: yTitle || "Wert", value: valueFormat(v), color }, ...detail])}`, e)
      );
      hit.addEventListener("mouseleave", hideTip);
      hit.addEventListener("mouseenter", () => rect.setAttribute("fill-opacity", 1));
      hit.addEventListener("mouseout", () => rect.setAttribute("fill-opacity", 0.92));
    });
    return;
  }

  // Vertical bars, for calendar years.
  const plot = frame(host, { height: height || 260, pad: { left: 56, right: 16, top: 10, bottom: 34 } });
  const lo = Math.min(0, ...finite);
  const hi = Math.max(0, ...finite);
  const y = (v) => plot.h - ((v - lo) / (hi - lo || 1)) * plot.h;
  yAxis(plot, y, niceTicks(lo, hi, 5), (t) => valueFormat(t, 0), yTitle);

  const slot = plot.w / labels.length;
  const barW = Math.max(3, slot - 4); // 2px surface gap each side
  labels.forEach((label, i) => {
    const v = values[i];
    const cx = i * slot + slot / 2;
    const color = v >= 0 ? "var(--pos)" : "var(--neg)";
    const top = Math.min(y(v), y(0));
    const h = Math.max(Math.abs(y(v) - y(0)), 1);
    const rect = el("rect", { x: cx - barW / 2, y: top, width: barW, height: h, rx: 3, fill: color, "fill-opacity": 0.92 }, plot.g);
    const hit = el("rect", { x: i * slot, y: 0, width: slot, height: plot.h, fill: "transparent" }, plot.g);
    const detail = extra ? extra(i) : [];
    hit.addEventListener("mousemove", (e) =>
      showTip(`<div class="t-title">${label}</div>${tipRows([{ label: yTitle || "Rendite", value: valueFormat(v), color }, ...detail])}`, e)
    );
    hit.addEventListener("mouseleave", hideTip);
    hit.addEventListener("mouseenter", () => rect.setAttribute("fill-opacity", 1));
    hit.addEventListener("mouseout", () => rect.setAttribute("fill-opacity", 0.92));
  });
  el("line", { x1: 0, x2: plot.w, y1: y(0), y2: y(0), stroke: "var(--border-strong)", "stroke-width": 1 }, plot.g);

  const idx = labelIndices(labels.length, Math.min(labels.length, 12));
  xAxisBand(plot, idx.map((i) => labels[i]), idx.map((i) => i * slot + slot / 2));
}

/* ----------------------------------------------------- grouped bar chart -- */
/* Several scenarios over the same categories (calendar years). */
export function groupedBarChart(host, { labels, groups, valueFormat = fmt.pctSigned, height = 300, yTitle = "" }) {
  if (!labels?.length || !groups?.length) {
    host.innerHTML = `<p class="muted">Keine Daten.</p>`;
    return;
  }
  const plot = frame(host, { height, pad: { left: 56, right: 16, top: 10, bottom: 34 } });
  const flat = groups.flatMap((g) => g.values).filter(Number.isFinite);
  const lo = Math.min(0, ...flat);
  const hi = Math.max(0, ...flat);
  const y = (v) => plot.h - ((v - lo) / (hi - lo || 1)) * plot.h;
  yAxis(plot, y, niceTicks(lo, hi, 5), (t) => valueFormat(t, 0), yTitle);

  const slot = plot.w / labels.length;
  const inner = Math.max(2, (slot - 6) / groups.length);
  const barW = Math.max(2, inner - 2); // 2px surface gap between adjacent bars

  labels.forEach((label, i) => {
    const base = i * slot + 3;
    groups.forEach((g, gi) => {
      const v = g.values[i];
      if (!Number.isFinite(v)) return;
      const color = g.color || seriesColor(gi);
      const top = Math.min(y(v), y(0));
      const h = Math.max(Math.abs(y(v) - y(0)), 1);
      el("rect", { x: base + gi * inner, y: top, width: barW, height: h, rx: 3, fill: color, "fill-opacity": 0.92 }, plot.g);
    });
    const hit = el("rect", { x: i * slot, y: 0, width: slot, height: plot.h, fill: "transparent" }, plot.g);
    hit.addEventListener("mousemove", (e) =>
      showTip(
        `<div class="t-title">${label}</div>${tipRows(
          groups.map((g, gi) => ({
            label: g.name,
            value: Number.isFinite(g.values[i]) ? valueFormat(g.values[i]) : "–",
            color: g.color || seriesColor(gi),
          }))
        )}`,
        e
      )
    );
    hit.addEventListener("mouseleave", hideTip);
  });
  el("line", { x1: 0, x2: plot.w, y1: y(0), y2: y(0), stroke: "var(--border-strong)", "stroke-width": 1 }, plot.g);

  const idx = labelIndices(labels.length, Math.min(labels.length, 14));
  xAxisBand(plot, idx.map((i) => labels[i]), idx.map((i) => i * slot + slot / 2));
}

/* ------------------------------------------------------ scatter / bullet -- */
/* The Markowitz bullet: frontier curve + single asset classes + portfolios.
   Every portfolio point carries a direct label, so identity never rests on
   colour alone even past the three-slot all-pairs cap. */
export function bulletChart(host, { frontier, assets, portfolios, markers = [], height = 420, xTitle = "Volatilität p.a.", yTitle = "Rendite p.a. (Erwartungswert)" }) {
  const xs = [
    ...frontier.map((p) => p.volatility),
    ...assets.map((a) => a.volatility),
    ...portfolios.map((p) => p.volatility),
    ...markers.map((m) => m.volatility),
  ].filter(Number.isFinite);
  const ys = [
    ...frontier.map((p) => p.y),
    ...assets.map((a) => a.y),
    ...portfolios.map((p) => p.y),
    ...markers.map((m) => m.y),
  ].filter(Number.isFinite);

  if (!xs.length) {
    host.innerHTML = `<p class="muted">Keine Effizienzlinie für diese Auswahl.</p>`;
    return;
  }

  const plot = frame(host, { height, pad: { left: 62, right: 30, top: 14, bottom: 44 } });
  const xLo = Math.min(0, ...xs);
  const xHi = Math.max(...xs) * 1.08;
  const yLo = Math.min(...ys) - (Math.max(...ys) - Math.min(...ys) || 0.01) * 0.1;
  const yHi = Math.max(...ys) + (Math.max(...ys) - Math.min(...ys) || 0.01) * 0.1;

  const X = (v) => ((v - xLo) / (xHi - xLo || 1)) * plot.w;
  const Y = (v) => plot.h - ((v - yLo) / (yHi - yLo || 1)) * plot.h;

  yAxis(plot, Y, niceTicks(yLo, yHi, 5), (t) => fmt.pct(t, 1), yTitle);

  const grid = el("g", { class: "grid" }, plot.g);
  const axis = el("g", { class: "axis", transform: `translate(0,${plot.h})` }, plot.g);
  el("line", { x1: 0, x2: plot.w, y1: 0, y2: 0 }, axis);
  for (const t of niceTicks(xLo, xHi, 6)) {
    if (t < xLo || t > xHi) continue;
    el("line", { x1: X(t), x2: X(t), y1: -plot.h, y2: 0 }, grid);
    const lab = el("text", { x: X(t), y: 16, "text-anchor": "middle" }, axis);
    lab.textContent = fmt.pct(t, 1);
  }
  const xt = el("text", { class: "axis-title", x: plot.w / 2, y: 36, "text-anchor": "middle" }, axis);
  xt.textContent = xTitle;

  // Frontier curve: one line, so no legend colour is spent on it.
  if (frontier.length > 1) {
    const d = frontier
      .map((p, i) => `${i ? "L" : "M"}${X(p.volatility).toFixed(2)},${Y(p.y).toFixed(2)}`)
      .join("");
    el("path", { d, class: "series-line", stroke: "var(--text-secondary)", "stroke-width": 2, "stroke-opacity": 0.55 }, plot.g);
  }

  // Single asset classes: hollow dots, recessive - context, not the subject.
  assets.forEach((a) => {
    const dot = el("circle", {
      cx: X(a.volatility), cy: Y(a.y), r: 4.5,
      fill: "var(--surface-1)", stroke: "var(--text-muted)", "stroke-width": 1.5,
    }, plot.g);
    dot.addEventListener("mousemove", (e) =>
      showTip(
        `<div class="t-title">${a.label}</div>${tipRows([
          { label: "Volatilität p.a.", value: fmt.pct(a.volatility) },
          { label: "Rendite p.a.", value: fmt.pct(a.y) },
          ...(a.extra || []),
        ])}`,
        e
      )
    );
    dot.addEventListener("mouseleave", hideTip);
  });

  // Reference markers (min-variance, max-Sharpe): shape carries the meaning.
  markers.forEach((m) => {
    const size = 6;
    const node = el("path", {
      d: `M${X(m.volatility)},${Y(m.y) - size}L${X(m.volatility) + size},${Y(m.y)}L${X(m.volatility)},${Y(m.y) + size}L${X(m.volatility) - size},${Y(m.y)}Z`,
      fill: "var(--surface-1)", stroke: "var(--text-primary)", "stroke-width": 1.8,
    }, plot.g);
    const lab = el("text", {
      x: X(m.volatility), y: Y(m.y) - size - 6, "text-anchor": "middle",
      "font-size": 10.5, fill: "var(--text-secondary)",
    }, plot.g);
    lab.textContent = m.label;
    node.addEventListener("mousemove", (e) =>
      showTip(
        `<div class="t-title">${m.label}</div>${tipRows([
          { label: "Volatilität p.a.", value: fmt.pct(m.volatility) },
          { label: "Rendite p.a.", value: fmt.pct(m.y) },
          ...(m.extra || []),
        ])}`,
        e
      )
    );
    node.addEventListener("mouseleave", hideTip);
  });

  // The simulated portfolios: filled, ringed against the surface, labelled.
  portfolios.forEach((p, i) => {
    const color = p.color || seriesColor(i);
    const dot = el("circle", { cx: X(p.volatility), cy: Y(p.y), r: 6.5, fill: color, class: "mark-ring" }, plot.g);
    const lab = el("text", {
      x: X(p.volatility) + 11, y: Y(p.y), "dominant-baseline": "middle",
      "font-size": 11.5, "font-weight": 600, fill: color,
    }, plot.g);
    lab.textContent = p.label;
    dot.addEventListener("mousemove", (e) =>
      showTip(
        `<div class="t-title">${p.label}</div>${tipRows([
          { label: "Volatilität p.a.", value: fmt.pct(p.volatility), color },
          { label: "Rendite p.a.", value: fmt.pct(p.y), color },
          ...(p.extra || []),
        ])}`,
        e
      )
    );
    dot.addEventListener("mouseleave", hideTip);
  });
}

/* ------------------------------------------------------------- heat matrix -- */
/* Correlations: a diverging ramp with a neutral midpoint, values printed in
   every cell so the colour is never the only channel. */
export function heatMatrix(host, { labels, matrix }) {
  if (!labels?.length) {
    host.innerHTML = `<p class="muted">Keine Daten.</p>`;
    return;
  }
  const n = labels.length;
  const cell = 40;
  const left = 190;
  const top = 128;
  // The column labels are rotated -45 deg and read up and to the right, so the
  // last one needs room past the final cell or it gets clipped.
  const right = 150;
  const width = left + n * cell + right;
  const height = top + n * cell + 12;

  host.innerHTML = "";
  const svg = el("svg", { viewBox: `0 0 ${width} ${height}`, role: "img" }, host);
  const g = el("g", { transform: `translate(${left},${top})` }, svg);

  const short = (s) => truncate(s, 24);

  labels.forEach((label, i) => {
    const rowLabel = el("text", {
      x: -10, y: i * cell + cell / 2, "text-anchor": "end", "dominant-baseline": "middle",
      "font-size": 11, fill: "var(--text-secondary)",
    }, g);
    rowLabel.textContent = short(label);

    const colLabel = el("text", {
      transform: `translate(${i * cell + cell / 2},-10) rotate(-45)`,
      "text-anchor": "start", "font-size": 11, fill: "var(--text-secondary)",
    }, g);
    colLabel.textContent = short(label);
  });

  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      const v = matrix[r]?.[c];
      const known = Number.isFinite(v);
      // Diverging: blue for positive, red for negative, neutral at zero.
      const strength = known ? Math.min(Math.abs(v), 1) : 0;
      const fill = !known
        ? "var(--surface-2)"
        : v >= 0
        ? `color-mix(in oklab, var(--pos) ${Math.round(strength * 78)}%, var(--mid))`
        : `color-mix(in oklab, var(--neg) ${Math.round(strength * 78)}%, var(--mid))`;

      // 2px surface gap between cells instead of a border.
      el("rect", {
        x: c * cell + 1, y: r * cell + 1, width: cell - 2, height: cell - 2,
        rx: 3, fill,
      }, g);

      const text = el("text", {
        x: c * cell + cell / 2, y: r * cell + cell / 2,
        "text-anchor": "middle", "dominant-baseline": "middle",
        "font-size": 10, "font-family": "var(--mono)",
        fill: strength > 0.6 ? "#ffffff" : "var(--text-primary)",
      }, g);
      text.textContent = known ? v.toFixed(2) : "–";

      const hit = el("rect", { x: c * cell, y: r * cell, width: cell, height: cell, fill: "transparent" }, g);
      hit.addEventListener("mousemove", (e) =>
        showTip(
          `<div class="t-title">Korrelation</div>${tipRows([
            { label: labels[r], value: "" },
            { label: labels[c], value: "" },
            { label: "Monatsrenditen", value: known ? v.toFixed(3) : "–" },
          ])}`,
          e
        )
      );
      hit.addEventListener("mouseleave", hideTip);
    }
  }
}

/* SAA-Tool - UI state, API calls and rendering. */

import {
  lineChart, barChart, groupedBarChart, bulletChart, heatMatrix,
  seriesColor, fmt,
} from "./charts.js";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const state = {
  boot: null,
  weights: {},        // asset class -> share (0..1)
  benchmarks: {},     // asset class -> ticker override
  ter: 0.0109,
  mode: "key_rate",
  start: "",
  end: "",
  draftName: "Neues Szenario",
  notes: "",
  compare: new Set(), // saved scenario names shown alongside the draft
  bounds: {},         // asset class -> {min, max} for the frontier
  lastSim: null,
  lastFrontier: null,
  tab: "kennzahlen",
};

const DRAFT = "Entwurf";
const LS_KEY = "saa-tool-draft-v1";

/* ------------------------------------------------------------------- utils -- */
const pctInput = (v) => (v * 100).toFixed(2).replace(/\.00$/, "");
const parsePct = (text) => {
  const value = parseFloat(String(text).replace(",", ".").replace("%", "").trim());
  return Number.isFinite(value) ? value / 100 : 0;
};
const sum = (obj) => Object.values(obj).reduce((a, b) => a + (Number(b) || 0), 0);

/* Colour follows the entity: the order comes from whatever was last
   simulated, so a scenario keeps its hue across tabs and a mode comparison
   does not paint both runs the same. */
function colorFor(name) {
  const order = state.seriesOrder?.length
    ? state.seriesOrder
    : [DRAFT, ...[...state.compare]];
  const i = order.indexOf(name);
  return seriesColor(i < 0 ? order.length : i);
}

function saveDraft() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({
      weights: state.weights, benchmarks: state.benchmarks, ter: state.ter,
      mode: state.mode,
      start: state.start, end: state.end, draftName: state.draftName,
      notes: state.notes, compare: [...state.compare], bounds: state.bounds,
    }));
  } catch { /* private window or blocked storage - the tool still works */ }
}

function loadDraft() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json().catch(() => ({ error: "Antwort war kein JSON." }));
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function setBusy(on, label = "rechnet") {
  const node = $("#status");
  node.innerHTML = on ? `<span class="spinner"></span> ${label} …` : "";
}

function notice(container, text, kind = "") {
  const div = document.createElement("div");
  div.className = `notice ${kind}`;
  div.innerHTML = `<span class="ico">${kind === "bad" ? "!" : kind === "warn" ? "!" : "i"}</span><span>${text}</span>`;
  container.appendChild(div);
}

/* -------------------------------------------------------------- mode switch -- */
function modeInfo(id) {
  return state.boot.modes.find((m) => m.id === id) || { id, label: id, hint: "" };
}

function renderModeSwitch() {
  const host = $("#mode-switch");
  host.innerHTML = "";
  for (const mode of state.boot.modes) {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", String(state.mode === mode.id));
    button.textContent = mode.label;
    button.title = mode.hint || "";
    button.addEventListener("click", () => {
      if (state.mode === mode.id) return;
      state.mode = mode.id;
      state.lastFrontier = null; // the frontier depends on the benchmarks
      renderModeSwitch();
      renderWeights();
      saveDraft();
      refresh();
    });
    host.appendChild(button);
  }

  const info = modeInfo(state.mode);
  const changed = (info.changes || []).length;
  $("#mode-hint").innerHTML =
    `${info.hint || ""}${
      changed
        ? ` <span class="muted">Betrifft ${changed} Klassen: ${info.changes.join(", ")}.</span>`
        : ""
    }`;
}

/* ------------------------------------------------------------ weight panel -- */
function renderWeights() {
  const host = $("#weights");
  host.innerHTML = "";

  for (const cls of state.boot.asset_classes) {
    const row = document.createElement("div");
    row.className = "weight-row";

    const current = cls.modes[state.mode] || cls.modes.index;

    const name = document.createElement("div");
    name.className = "name";
    name.innerHTML = `<span class="label" title="${cls.name}">${cls.name}</span>`;
    if (cls.mode_differs) {
      const tag = document.createElement("span");
      tag.className = "mode-tag";
      tag.textContent = "MODUS";
      tag.title =
        `Diese Klasse hängt am Benchmark-Modus:\n` +
        `• Marktindizes: ${cls.modes.index.benchmark}\n` +
        `• Geldmarkt + Aufschlag: ${cls.modes.key_rate.benchmark}`;
      name.appendChild(tag);
    }
    if (current.proxy && !state.benchmarks[cls.name]) {
      const flag = document.createElement("span");
      flag.className = "proxy-flag";
      flag.textContent = "PROXY";
      flag.title = current.note || "Der Benchmark ist nur ein Behelf für diese Assetklasse.";
      name.appendChild(flag);
    }

    const box = document.createElement("input");
    box.type = "text";
    box.className = "pct";
    box.value = pctInput(state.weights[cls.name] ?? 0);
    box.setAttribute("aria-label", `Gewicht ${cls.name} in Prozent`);

    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = "0";
    slider.max = "100";
    slider.step = "0.5";
    slider.value = String((state.weights[cls.name] ?? 0) * 100);
    slider.setAttribute("aria-label", `Gewicht ${cls.name}`);

    const bench = document.createElement("div");
    bench.className = "bench";
    const select = document.createElement("select");
    select.setAttribute("aria-label", `Benchmark ${cls.name}`);
    const auto = document.createElement("option");
    auto.value = "";
    auto.textContent = `automatisch · ${current.benchmark}`;
    select.appendChild(auto);
    for (const choice of cls.choices) {
      const option = document.createElement("option");
      option.value = choice.ticker;
      option.textContent = `${choice.ticker} · ${choice.label || ""} (ab ${choice.first_month})`;
      select.appendChild(option);
    }
    select.value = state.benchmarks[cls.name] || "";
    bench.appendChild(select);

    const push = (value) => {
      state.weights[cls.name] = value;
      box.value = pctInput(value);
      slider.value = String(value * 100);
      renderSums();
      saveDraft();
    };
    box.addEventListener("change", () => push(Math.max(0, parsePct(box.value))));
    slider.addEventListener("input", () => push(Number(slider.value) / 100));
    select.addEventListener("change", () => {
      if (select.value) state.benchmarks[cls.name] = select.value;
      else delete state.benchmarks[cls.name];
      state.lastFrontier = null;
      saveDraft();
      renderWeights();
      refresh();
    });

    row.append(name, box, slider, bench);
    host.appendChild(row);
  }
  renderSums();
}

function renderSums() {
  const groups = {};
  for (const cls of state.boot.asset_classes) {
    const key = cls.group || "Ohne Gruppe";
    groups[key] = (groups[key] || 0) + (state.weights[cls.name] || 0);
  }
  const host = $("#group-sums");
  host.innerHTML = Object.entries(groups)
    .map(([key, value]) => `<div><span>${key}</span><b>${fmt.pct(value, 1)}</b></div>`)
    .join("");

  const total = sum(state.weights);
  const row = $("#total-row");
  row.classList.toggle("off", Math.abs(total - 1) > 0.0005);
  $("#total-value").textContent = fmt.pct(total, 2);
  $("#normalise-hint").textContent =
    Math.abs(total - 1) > 0.0005
      ? "wird für die Simulation auf 100 % normiert"
      : "";
}

/* ---------------------------------------------------------- scenario panel -- */
function renderScenarios() {
  const host = $("#scenario-list");
  host.innerHTML = "";

  const draftItem = document.createElement("div");
  draftItem.className = "scenario-item active";
  draftItem.innerHTML = `
    <span class="swatch" style="background:${seriesColor(0)}"></span>
    <span class="nm"><b>${DRAFT}</b> <span class="muted">(aktuelle Gewichte)</span></span>
    <span class="muted mono">${modeInfo(state.mode).label}</span>
    <span></span>`;
  host.appendChild(draftItem);

  state.boot.scenarios.forEach((scenario) => {
    const item = document.createElement("div");
    const on = state.compare.has(scenario.name);
    item.className = `scenario-item${on ? " active" : ""}`;

    const check = document.createElement("input");
    check.type = "checkbox";
    check.checked = on;
    check.setAttribute("aria-label", `${scenario.name} vergleichen`);
    check.addEventListener("change", () => {
      if (check.checked) state.compare.add(scenario.name);
      else state.compare.delete(scenario.name);
      saveDraft();
      renderScenarios();
      refresh();
    });

    const label = document.createElement("span");
    label.className = "nm";
    const scenarioMode = modeInfo(scenario.mode || "key_rate");
    label.title = `${scenario.notes || scenario.name}\nModus: ${scenarioMode.label}`;
    label.innerHTML =
      `${scenario.name} <span class="muted" style="font-size:11px">· ${scenarioMode.label}</span>`;

    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = on ? colorFor(scenario.name) : "var(--border-strong)";

    const load = document.createElement("button");
    load.className = "ghost";
    load.textContent = "laden";
    load.title = "Gewichte dieses Szenarios in den Entwurf übernehmen";
    load.addEventListener("click", () => {
      state.weights = {};
      for (const cls of state.boot.asset_classes) {
        state.weights[cls.name] = scenario.weights[cls.name] ?? 0;
      }
      state.benchmarks = { ...scenario.benchmarks };
      state.ter = scenario.ter;
      state.mode = scenario.mode || "key_rate";
      state.draftName = scenario.name;
      state.notes = scenario.notes || "";
      state.lastFrontier = null;
      $("#ter").value = (scenario.ter * 100).toFixed(2);
      $("#scenario-name").value = scenario.name;
      $("#scenario-notes").value = scenario.notes || "";
      renderModeSwitch();
      renderWeights();
      saveDraft();
      refresh();
    });

    const del = document.createElement("button");
    del.className = "ghost";
    del.textContent = "×";
    del.title = "Szenario löschen";
    del.addEventListener("click", async () => {
      if (!confirm(`Szenario "${scenario.name}" wirklich löschen?`)) return;
      await api(`/api/scenario?name=${encodeURIComponent(scenario.name)}`, { method: "DELETE" });
      state.compare.delete(scenario.name);
      await reload();
    });

    const tail = document.createElement("span");
    tail.style.display = "flex";
    tail.append(load, del);

    item.append(check, label, swatch, tail);
    host.appendChild(item);
  });
}

/* ------------------------------------------------------------------ driver -- */
function draftScenario() {
  return {
    name: DRAFT,
    weights: state.weights,
    benchmarks: state.benchmarks,
    ter: state.ter,
    notes: state.notes,
    mode: state.mode,
  };
}

function activeScenarios() {
  const chosen = state.boot.scenarios.filter((s) => state.compare.has(s.name));
  return [draftScenario(), ...chosen];
}

async function refresh(extraScenarios = null) {
  setBusy(true);
  try {
    const payload = await api("/api/simulate", {
      method: "POST",
      body: JSON.stringify({
        scenarios: extraScenarios || activeScenarios(),
        start: state.start,
        end: state.end,
      }),
    });
    state.lastSim = payload;
    state.seriesOrder = (payload.results || []).map((r) => r.scenario.name);
    renderActiveTab();
  } catch (error) {
    state.lastSim = null;
    $("#view").innerHTML = "";
    notice($("#view"), `Simulation fehlgeschlagen: ${error.message}`, "bad");
  } finally {
    setBusy(false);
  }
}

/* Same weights, once per benchmark mode - the clearest way to see what the
   switch is actually worth. */
function compareModes() {
  return refresh(
    state.boot.modes.map((mode) => ({
      ...draftScenario(),
      name: modeInfo(mode.id).label,
      mode: mode.id,
    }))
  );
}

async function loadFrontier() {
  setBusy(true, "Effizienzlinie");
  try {
    state.lastFrontier = await api("/api/frontier", {
      method: "POST",
      body: JSON.stringify({
        asset_classes: state.boot.asset_classes.map((c) => c.name),
        benchmarks: state.benchmarks,
        bounds: state.bounds,
        mode: state.mode,
        start: state.start,
        end: state.end,
        points: 36,
      }),
    });
  } catch (error) {
    state.lastFrontier = { error: error.message, points: [] };
  } finally {
    setBusy(false);
  }
}

async function reload() {
  state.boot = await api("/api/bootstrap");
  renderModeSwitch();
  renderWeights();
  renderScenarios();
  await refresh();
}

/* ------------------------------------------------------------------- views -- */
function renderActiveTab() {
  $$(".tabs button").forEach((b) =>
    b.setAttribute("aria-selected", String(b.dataset.tab === state.tab))
  );
  const view = $("#view");
  view.innerHTML = "";
  if (!state.lastSim) return;

  const { results, comparison, correlation } = state.lastSim;
  for (const result of results) {
    for (const warning of result.warnings || []) {
      notice(view, `<b>${result.scenario.name}:</b> ${warning}`, "warn");
    }
  }

  // One line per scenario that is standing on a stand-in benchmark, naming the
  // classes and how much weight sits on them.
  for (const result of results) {
    const proxies = result.proxy_members || [];
    if (!proxies.length) continue;
    const share = proxies.reduce((a, b) => a + b.weight, 0);
    const label = results.length > 1 ? `<b>${result.scenario.name}:</b> ` : "";
    notice(
      view,
      `${label}<b>Behelfs-Benchmark bei ${fmt.pct(share, 0)} des Portfolios</b> –
       ${proxies.map((x) => `${x.asset_class} <span class="mono">(${x.benchmark})</span>`).join(", ")}.
       ${
         (result.scenario.mode || "key_rate") === "key_rate"
           ? `Geldmarkt + Aufschlag ist eine nahezu gerade Linie ohne eigenes Risiko –
              Vola, Sharpe und Effizienzlinie fallen zu gut aus.
              Der Modus <b>Marktindizes</b> zeigt die realistischere Variante.`
           : `Für diese Klassen gibt es noch keinen echten Index, siehe
              <span class="mono">docs/benchmark-mapping.md</span>.`
       }`,
      "warn"
    );
  }

  const renderers = {
    kennzahlen: () => viewKennzahlen(view, results, comparison),
    verlauf: () => viewVerlauf(view, results, comparison),
    bullet: () => viewBullet(view, results),
    beitraege: () => viewBeitraege(view, results),
    korrelation: () => viewKorrelation(view, correlation),
    jahre: () => viewJahre(view, results, comparison),
  };
  (renderers[state.tab] || renderers.kennzahlen)();
}

function card(parent, title, hint) {
  const node = document.createElement("section");
  node.className = "card";
  node.innerHTML = `<h2>${title}</h2>${hint ? `<p class="hint">${hint}</p>` : ""}`;
  parent.appendChild(node);
  return node;
}

function legendFor(names) {
  return `<div class="legend">${names
    .map(
      (n) =>
        `<span class="item"><span class="key line" style="background:${colorFor(n)}"></span>${n}</span>`
    )
    .join("")}</div>`;
}

/* -- 1. key figures ------------------------------------------------------- */
function viewKennzahlen(view, results, comparison) {
  const first = results[0];
  if (!first || !first.months.length) {
    notice(view, "Kein Monat mit vollständigen Daten - bitte Gewichte oder Zeitraum prüfen.", "bad");
    return;
  }

  const tiles = card(
    view,
    `${first.scenario.name} auf einen Blick`,
    `Benchmark-Modus <b>${modeInfo(first.scenario.mode || "key_rate").label}</b> ·
     Zeitraum ${first.stats.start} bis ${first.stats.end}, ${first.stats.months} Monate ·
     netto nach Kosten von ${fmt.pct(first.scenario.ter, 2)} p.a.`
  );
  const box = document.createElement("div");
  box.className = "tiles";
  const s = first.stats;
  const tileData = [
    ["Rendite p.a.", fmt.pct(s.cagr), `Gesamt ${fmt.pct(s.total_return, 1)}`],
    ["Volatilität p.a.", fmt.pct(s.volatility), `Schlechtester Monat ${fmt.pct(s.worst_month)}`],
    ["Sharpe Ratio", fmt.num(s.sharpe), `risikolos ${fmt.pct(s.risk_free_cagr)} p.a.`],
    ["Max Drawdown", fmt.pct(s.max_drawdown), s.drawdown.trough_month ? `Tief ${s.drawdown.trough_month}` : ""],
    ["Calmar Ratio", fmt.num(s.calmar), "Rendite p.a. / |MaxDD|"],
    ["Positive Monate", fmt.pct(s.positive_share, 1), `${s.months} Monate`],
  ];
  box.innerHTML = tileData
    .map(([k, v, n]) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="n">${n}</div></div>`)
    .join("");
  tiles.appendChild(box);

  // The comparison table is also the relief for the light-mode contrast WARN:
  // every charted value is readable as a number here.
  const compareCard = card(
    view,
    "Kennzahlenvergleich",
    comparison
      ? `Alle Szenarien über den gemeinsamen Zeitraum ${comparison.months[0]} bis ${comparison.months.at(-1)} (${comparison.months.length} Monate), damit die Zahlen vergleichbar sind.`
      : "Weitere Szenarien links anhaken, um sie hier gegenüberzustellen."
  );

  const modeByName = {};
  for (const entry of results) modeByName[entry.scenario.name] = entry.scenario.mode || "key_rate";
  const rows = comparison
    ? comparison.scenarios.map((entry) => ({ name: entry.name, stats: entry.stats }))
    : results.map((entry) => ({ name: entry.scenario.name, stats: entry.stats }));

  const metricRows = [
    ["Benchmark-Modus", (st, name) => modeInfo(modeByName[name] || "key_rate").label, "text"],
    ["Zeitraum", (st) => `${st.start} – ${st.end}`, "text"],
    ["Monate", (st) => String(st.months), "num"],
    ["Total Return", (st) => fmt.pct(st.total_return, 1), "num"],
    ["Rendite p.a.", (st) => fmt.pct(st.cagr), "num"],
    ["Volatilität p.a.", (st) => fmt.pct(st.volatility), "num"],
    ["Sharpe Ratio", (st) => fmt.num(st.sharpe), "num"],
    ["Sortino Ratio", (st) => fmt.num(st.sortino), "num"],
    ["Max Drawdown", (st) => fmt.pct(st.max_drawdown), "num"],
    ["Tief des Drawdowns", (st) => fmt.month(st.drawdown.trough_month), "text"],
    ["Erholung", (st) => (st.drawdown.recovery_month ? `${st.drawdown.recovery_month} (${st.drawdown.months_to_recovery} M.)` : "noch nicht"), "text"],
    ["Calmar Ratio", (st) => fmt.num(st.calmar), "num"],
    ["Bester Monat", (st) => fmt.pct(st.best_month), "num"],
    ["Schlechtester Monat", (st) => fmt.pct(st.worst_month), "num"],
    ["Positive Monate", (st) => fmt.pct(st.positive_share, 1), "num"],
    ["VaR 95 % (Monat)", (st) => fmt.pct(st.var_95), "num"],
    ["CVaR 95 % (Monat)", (st) => fmt.pct(st.cvar_95), "num"],
  ];

  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  wrap.innerHTML = `
    <table class="data">
      <thead><tr><th>Kennzahl</th>${rows
        .map((r) => `<th><span class="mark" style="background:${colorFor(r.name)}"></span>${r.name}</th>`)
        .join("")}</tr></thead>
      <tbody>${metricRows
        .map(
          ([label, pick, kind]) =>
            `<tr><td>${label}</td>${rows
              .map((r) => `<td class="${kind === "num" ? "num" : ""}">${pick(r.stats, r.name)}</td>`)
              .join("")}</tr>`
        )
        .join("")}</tbody>
    </table>`;
  compareCard.appendChild(wrap);

  if (first.window_limited_by?.length) {
    const info = card(view, "Was den Zeitraum begrenzt", "Die kürzeste Historie unter den gewichteten Benchmarks bestimmt den Start der Simulation.");
    const list = document.createElement("ul");
    list.style.margin = "0";
    list.style.paddingLeft = "18px";
    list.style.fontSize = "12.5px";
    list.style.color = "var(--text-secondary)";
    list.innerHTML = first.window_limited_by.map((x) => `<li class="mono">${x}</li>`).join("");
    info.appendChild(list);
  }
}

/* -- 2. performance and drawdown ----------------------------------------- */
function viewVerlauf(view, results, comparison) {
  const entries = comparison
    ? comparison.scenarios.map((e) => ({ name: e.name, wealth: e.wealth, drawdown: e.drawdown }))
    : results.filter((r) => r.months.length).map((r) => ({ name: r.scenario.name, wealth: r.wealth, drawdown: r.drawdown }));
  const months = comparison ? comparison.months : results[0]?.months || [];

  if (!months.length) {
    notice(view, "Kein gemeinsamer Zeitraum für den Verlauf.", "bad");
    return;
  }

  const perf = card(view, "Wertentwicklung, indexiert auf 100", `Monatlich rebalanciert, netto nach Kosten. ${months[0]} = 100.`);
  const head = document.createElement("div");
  head.className = "chart-head";
  head.innerHTML = legendFor(entries.map((e) => e.name));
  const toggle = document.createElement("div");
  toggle.className = "toggle-row";
  toggle.innerHTML = `<label><input type="checkbox" id="log-scale"> logarithmische Achse</label>`;
  head.appendChild(toggle);
  perf.appendChild(head);

  const figure = document.createElement("figure");
  figure.className = "chart";
  perf.appendChild(figure);
  const caption = document.createElement("figcaption");
  caption.textContent = "Linien sind am rechten Rand direkt beschriftet; Werte im Tooltip.";
  perf.appendChild(caption);

  const drawPerf = (log) =>
    lineChart(figure, {
      months,
      series: entries.map((e) => ({ name: e.name, shortName: e.name, color: colorFor(e.name), values: e.wealth })),
      yFormat: fmt.idx,
      yTitle: "Index",
      logScale: log,
      height: 360,
    });
  drawPerf(false);
  $("#log-scale").addEventListener("change", (event) => drawPerf(event.target.checked));

  const dd = card(view, "Drawdown-Verlauf", "Abstand zum bisherigen Höchststand, Monatsendwerte.");
  dd.insertAdjacentHTML("beforeend", legendFor(entries.map((e) => e.name)));
  const ddFigure = document.createElement("figure");
  ddFigure.className = "chart";
  dd.appendChild(ddFigure);
  lineChart(ddFigure, {
    months,
    series: entries.map((e) => ({
      name: e.name, shortName: e.name, color: colorFor(e.name),
      values: e.drawdown, fillToZero: entries.length === 1,
    })),
    yFormat: (v) => fmt.pct(v, 0),
    yTitle: "Drawdown",
    zeroLine: true,
    height: 280,
    valueFormat: (v) => fmt.pct(v, 2),
  });

  const first = results.find((r) => r.months.length);
  if (first?.rolling?.months?.length) {
    const roll = card(view, `Rollierende ${first.rolling.window} Monate`, "Annualisierte Rendite und Volatilität über ein gleitendes Fenster - zeigt, wie stabil das Profil über die Zeit war.");
    roll.insertAdjacentHTML(
      "beforeend",
      `<div class="legend">
        <span class="item"><span class="key line" style="background:${seriesColor(0)}"></span>Rendite p.a.</span>
        <span class="item"><span class="key line" style="background:${seriesColor(1)}"></span>Volatilität p.a.</span>
      </div>`
    );
    const rollFigure = document.createElement("figure");
    rollFigure.className = "chart";
    roll.appendChild(rollFigure);
    // Both series are percentages per annum, so one axis is correct here.
    lineChart(rollFigure, {
      months: first.rolling.months,
      series: [
        { name: "Rendite p.a.", shortName: "Rendite", color: seriesColor(0), values: first.rolling.return },
        { name: "Volatilität p.a.", shortName: "Vola", color: seriesColor(1), values: first.rolling.volatility },
      ],
      yFormat: (v) => fmt.pct(v, 0),
      yTitle: "p.a.",
      zeroLine: true,
      height: 280,
      valueFormat: (v) => fmt.pct(v, 2),
    });
    roll.insertAdjacentHTML("beforeend", `<figcaption>Gilt für "${first.scenario.name}".</figcaption>`);
  }
}

/* -- 3. Markowitz bullet -------------------------------------------------- */
async function viewBullet(view, results) {
  const host = card(
    view,
    "Markowitz-Bullet",
    "Effizienzlinie über die konfigurierten Assetklassen: long only, voll investiert, " +
      "optional mit Ober- und Untergrenzen. Optimiert wird im Mean-Variance-Sinn auf " +
      "arithmetische Erwartungswerte; die Punkte der Szenarien sind brutto vor Kosten, " +
      "damit sie auf derselben Achse liegen wie die Linie."
  );

  const controls = document.createElement("div");
  controls.className = "toggle-row";
  controls.style.marginBottom = "12px";
  controls.innerHTML = `
    <button id="frontier-run" class="primary">Effizienzlinie berechnen</button>
    <label>Obergrenze je Klasse
      <input type="text" id="cap-all" class="pct" style="width:60px" value="100" aria-label="Obergrenze je Klasse in Prozent">
    </label>
    <span class="muted">Rechenzeit ca. 2-3 s, Ergebnisse werden zwischengespeichert.</span>`;
  host.appendChild(controls);

  const figure = document.createElement("figure");
  figure.className = "chart";
  host.appendChild(figure);
  const info = document.createElement("div");
  host.appendChild(info);

  const paint = () => {
    const payload = state.lastFrontier;
    if (!payload) {
      figure.innerHTML = `<p class="muted">Noch nicht berechnet.</p>`;
      return;
    }
    if (payload.error) {
      figure.innerHTML = "";
      notice(info, payload.error, "bad");
      return;
    }

    const portfolios = results
      .filter((r) => r.months.length)
      .map((r) => ({
        label: r.scenario.name,
        volatility: r.gross_stats.volatility,
        y: r.gross_stats.cagr,
        color: colorFor(r.scenario.name),
        extra: [
          { label: "Sharpe (brutto)", value: fmt.num(r.gross_stats.sharpe) },
          { label: "netto Rendite p.a.", value: fmt.pct(r.stats.cagr) },
        ],
      }));

    const markers = [];
    if (payload.min_variance) {
      markers.push({
        label: "Min-Varianz",
        volatility: payload.min_variance.volatility,
        y: payload.min_variance.cagr,
        extra: topWeights(payload.min_variance.weights),
      });
    }
    if (payload.max_sharpe) {
      markers.push({
        label: "Max-Sharpe",
        volatility: payload.max_sharpe.volatility,
        y: payload.max_sharpe.cagr,
        extra: [
          { label: "Sharpe", value: fmt.num(payload.max_sharpe.sharpe) },
          ...topWeights(payload.max_sharpe.weights),
        ],
      });
    }

    bulletChart(figure, {
      frontier: payload.points.map((p) => ({ volatility: p.volatility, y: p.cagr })),
      assets: payload.assets.map((a) => ({
        label: a.asset_class,
        volatility: a.volatility,
        y: a.cagr,
        extra: [{ label: "Sharpe", value: fmt.num(a.sharpe) }],
      })),
      portfolios,
      markers,
      height: 440,
    });

    info.innerHTML = `
      <div class="legend" style="margin-top:10px">
        <span class="item"><span class="key line" style="background:var(--text-secondary)"></span>Effizienzlinie</span>
        <span class="item"><span class="key" style="background:var(--surface-1);border:1.5px solid var(--text-muted);border-radius:50%"></span>einzelne Assetklasse</span>
        <span class="item"><span class="key" style="background:var(--surface-1);border:1.8px solid var(--text-primary);transform:rotate(45deg)"></span>Min-Varianz / Max-Sharpe</span>
        ${portfolios.map((p) => `<span class="item"><span class="key" style="background:${p.color};border-radius:50%"></span>${p.label}</span>`).join("")}
      </div>
      <p class="hint" style="margin-top:10px">Fenster ${payload.window?.start} bis ${payload.window?.end} (${payload.window?.months} Monate).
      ${payload.proxy_classes?.length ? `<b>Achtung:</b> ${payload.proxy_classes.join(", ")} laufen auf Platzhalter-Benchmarks; die Linie überschätzt dort das Rendite-Risiko-Verhältnis.` : ""}</p>`;

    if (payload.max_sharpe) {
      const table = document.createElement("div");
      table.className = "table-wrap";
      const names = state.boot.asset_classes.map((c) => c.name);
      table.innerHTML = `
        <table class="data">
          <thead><tr><th>Assetklasse</th><th>Entwurf</th><th>Min-Varianz</th><th>Max-Sharpe</th></tr></thead>
          <tbody>${names
            .map(
              (n) =>
                `<tr><td>${n}</td>
                 <td class="num">${fmt.pct(state.weights[n] || 0, 1)}</td>
                 <td class="num">${fmt.pct(payload.min_variance?.weights?.[n] || 0, 1)}</td>
                 <td class="num">${fmt.pct(payload.max_sharpe?.weights?.[n] || 0, 1)}</td></tr>`
            )
            .join("")}</tbody>
        </table>`;
      const weightsCard = card(view, "Optimale Gewichte im Vergleich", "Zum Übernehmen die Zahlen links eintragen - das Tool überschreibt den Entwurf nicht von selbst.");
      weightsCard.appendChild(table);
    }
  };

  $("#frontier-run").addEventListener("click", async () => {
    const cap = Math.min(1, Math.max(0.01, parsePct($("#cap-all").value) || 1));
    state.bounds = {};
    if (cap < 1) {
      for (const cls of state.boot.asset_classes) state.bounds[cls.name] = { min: 0, max: cap };
    }
    saveDraft();
    await loadFrontier();
    info.innerHTML = "";
    paint();
  });

  if (state.lastFrontier) paint();
  else figure.innerHTML = `<p class="muted">Auf "Effizienzlinie berechnen" klicken.</p>`;
}

function topWeights(weights) {
  return Object.entries(weights || {})
    .filter(([, v]) => v > 0.005)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([k, v]) => ({ label: k, value: fmt.pct(v, 1) }));
}

/* -- 4. contributions ----------------------------------------------------- */
function viewBeitraege(view, results) {
  const first = results.find((r) => r.months.length);
  if (!first) {
    notice(view, "Keine Daten für die Beitragsrechnung.", "bad");
    return;
  }

  const perf = card(
    view,
    "Performancebeitrag je Assetklasse",
    `Aufgezinster Beitrag der gewichteten Monatsrenditen über ${first.stats.start} bis ${first.stats.end} - dieselbe Rechnung wie in BM-Tool, Zeilen 58-62.`
  );
  const perfFigure = document.createElement("figure");
  perfFigure.className = "chart";
  perf.appendChild(perfFigure);
  const contributions = first.performance_contribution;
  barChart(perfFigure, {
    labels: contributions.map((c) => c.asset_class),
    values: contributions.map((c) => c.contribution),
    valueFormat: (v, d = 1) => fmt.pctSigned(v, d),
    yTitle: "Beitrag",
    extra: (i) => [
      { label: "Gewicht", value: fmt.pct(contributions[i].weight, 1) },
      { label: "Anteil am Gesamtbeitrag", value: fmt.pct(contributions[i].share, 1) },
      { label: "Benchmark", value: contributions[i].benchmark },
    ],
  });

  const risk = card(
    view,
    "Risikobeitrag je Assetklasse",
    "Komponentenrisiko <span class='mono'>w · (Σw) / σ</span>, annualisiert. Die Beiträge summieren sich auf die Portfoliovolatilität - anders als die Gewichte sagen sie, wo das Risiko wirklich herkommt."
  );
  const riskFigure = document.createElement("figure");
  riskFigure.className = "chart";
  risk.appendChild(riskFigure);
  const rc = first.risk_contribution;
  barChart(riskFigure, {
    labels: rc.map((r) => r.asset_class),
    values: rc.map((r) => r.component_risk),
    valueFormat: (v, d = 2) => fmt.pct(v, d),
    yTitle: "Risikobeitrag p.a.",
    extra: (i) => [
      { label: "Gewicht", value: fmt.pct(rc[i].weight, 1) },
      { label: "Anteil am Gesamtrisiko", value: fmt.pct(rc[i].share, 1) },
      { label: "Eigenvola p.a.", value: fmt.pct(rc[i].volatility) },
      { label: "Marginales Risiko", value: fmt.pct(rc[i].marginal_risk) },
    ],
  });

  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  wrap.innerHTML = `
    <table class="data">
      <thead><tr>
        <th>Assetklasse</th><th>Benchmark</th><th>Gewicht</th>
        <th>Perf.-Beitrag</th><th>Anteil Perf.</th>
        <th>Eigenvola p.a.</th><th>Risikobeitrag</th><th>Anteil Risiko</th>
      </tr></thead>
      <tbody>${first.members
        .map((name, i) => {
          const c = contributions[i];
          const r = rc[i];
          return `<tr>
            <td>${name}</td><td class="mono" style="font-size:11px">${c.benchmark}</td>
            <td class="num">${fmt.pct(c.weight, 1)}</td>
            <td class="num ${c.contribution >= 0 ? "up" : "down"}">${fmt.pctSigned(c.contribution, 1)}</td>
            <td class="num">${fmt.pct(c.share, 1)}</td>
            <td class="num">${fmt.pct(r.volatility)}</td>
            <td class="num">${fmt.pct(r.component_risk)}</td>
            <td class="num">${fmt.pct(r.share, 1)}</td>
          </tr>`;
        })
        .join("")}</tbody>
    </table>`;
  card(view, "Beiträge als Tabelle", "Dieselben Zahlen zum Kopieren.").appendChild(wrap);
}

/* -- 5. correlations ------------------------------------------------------ */
function viewKorrelation(view, correlation) {
  if (!correlation?.asset_classes?.length) {
    notice(view, "Für die Korrelationen braucht es mindestens zwei gewichtete Assetklassen.", "warn");
    return;
  }
  const host = card(
    view,
    "Korrelationsmatrix der Monatsrenditen",
    "Nur die Klassen mit Gewicht > 0, über den gemeinsamen Zeitraum des Entwurfs. Blau = gleichläufig, rot = gegenläufig."
  );
  const figure = document.createElement("figure");
  figure.className = "chart";
  figure.style.overflowX = "auto";
  host.appendChild(figure);
  heatMatrix(figure, { labels: correlation.asset_classes, matrix: correlation.matrix });
  host.insertAdjacentHTML(
    "beforeend",
    `<figcaption>Werte stehen in jeder Zelle, die Farbe ist nur Unterstützung.</figcaption>`
  );
}

/* -- 6. calendar years ---------------------------------------------------- */
function viewJahre(view, results, comparison) {
  const entries = comparison
    ? comparison.scenarios.map((e) => ({ name: e.name, years: e.calendar_years }))
    : results.filter((r) => r.months.length).map((r) => ({ name: r.scenario.name, years: r.calendar_years }));
  if (!entries.length) {
    notice(view, "Keine Jahresdaten.", "bad");
    return;
  }

  const years = [...new Set(entries.flatMap((e) => e.years.map((y) => y.year)))].sort();
  const host = card(
    view,
    "Kalenderjahresrenditen",
    "Netto nach Kosten. Angeschnittene Jahre am Anfang und Ende sind mit * markiert."
  );
  host.insertAdjacentHTML("beforeend", legendFor(entries.map((e) => e.name)));
  const figure = document.createElement("figure");
  figure.className = "chart";
  host.appendChild(figure);

  const labelled = years.map((y) => {
    const partial = entries.some((e) => e.years.find((x) => x.year === y)?.partial);
    return partial ? `${y}*` : y;
  });

  if (entries.length === 1) {
    const series = years.map((y) => entries[0].years.find((x) => x.year === y)?.return ?? null);
    barChart(figure, {
      labels: labelled, values: series, horizontal: false, height: 300,
      valueFormat: (v, d = 1) => fmt.pctSigned(v, d), yTitle: "Jahresrendite",
      extra: (i) => [{ label: "Monate im Jahr", value: String(entries[0].years.find((x) => x.year === years[i])?.months ?? "–") }],
    });
  } else {
    groupedBarChart(figure, {
      labels: labelled,
      groups: entries.map((e) => ({
        name: e.name,
        color: colorFor(e.name),
        values: years.map((y) => e.years.find((x) => x.year === y)?.return ?? null),
      })),
      valueFormat: (v, d = 1) => fmt.pctSigned(v, d),
      yTitle: "Jahresrendite",
      height: 320,
    });
  }

  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  wrap.innerHTML = `
    <table class="data">
      <thead><tr><th>Jahr</th>${entries
        .map((e) => `<th><span class="mark" style="background:${colorFor(e.name)}"></span>${e.name}</th>`)
        .join("")}</tr></thead>
      <tbody>${years
        .map((y, i) => {
          return `<tr><td class="mono">${labelled[i]}</td>${entries
            .map((e) => {
              const hit = e.years.find((x) => x.year === y);
              if (!hit) return `<td class="num">–</td>`;
              return `<td class="num ${hit.return >= 0 ? "up" : "down"}">${fmt.pctSigned(hit.return, 2)}</td>`;
            })
            .join("")}</tr>`;
        })
        .join("")}</tbody>
    </table>`;
  card(view, "Jahresrenditen als Tabelle", "").appendChild(wrap);
}

/* -------------------------------------------------------------------- init -- */
async function init() {
  state.boot = await api("/api/bootstrap");

  const saved = loadDraft();
  const names = state.boot.asset_classes.map((c) => c.name);
  if (saved?.weights && Object.keys(saved.weights).length) {
    for (const name of names) state.weights[name] = saved.weights[name] ?? 0;
    state.benchmarks = saved.benchmarks || {};
    state.ter = Number.isFinite(saved.ter) ? saved.ter : 0.0109;
    state.mode = state.boot.modes.some((m) => m.id === saved.mode)
      ? saved.mode
      : state.boot.default_mode;
    state.start = saved.start || "";
    state.end = saved.end || "";
    state.draftName = saved.draftName || "Neues Szenario";
    state.notes = saved.notes || "";
    state.bounds = saved.bounds || {};
    (saved.compare || []).forEach((n) => {
      if (state.boot.scenarios.some((s) => s.name === n)) state.compare.add(n);
    });
  } else {
    const seed = state.boot.scenarios[0];
    for (const name of names) state.weights[name] = seed?.weights?.[name] ?? 0;
    state.ter = seed?.ter ?? 0.0109;
    state.mode = seed?.mode || state.boot.default_mode;
    state.draftName = seed ? `${seed.name} (Kopie)` : "Neues Szenario";
  }

  $("#ter").value = (state.ter * 100).toFixed(2);
  $("#scenario-name").value = state.draftName;
  $("#scenario-notes").value = state.notes;
  $("#start").value = state.start;
  $("#end").value = state.end;
  $("#period-hint").textContent = `Daten vorhanden von ${state.boot.months.first} bis ${state.boot.months.last}.`;
  $("#risk-free-label").textContent = `${state.boot.risk_free.ticker}`;

  renderModeSwitch();
  renderWeights();
  renderScenarios();

  $("#compare-modes").addEventListener("click", compareModes);

  $("#ter").addEventListener("change", (e) => {
    state.ter = Math.max(0, parsePct(e.target.value));
    e.target.value = (state.ter * 100).toFixed(2);
    saveDraft();
    refresh();
  });
  $("#start").addEventListener("change", (e) => { state.start = e.target.value.trim(); saveDraft(); refresh(); });
  $("#end").addEventListener("change", (e) => { state.end = e.target.value.trim(); saveDraft(); refresh(); });
  $("#scenario-name").addEventListener("input", (e) => { state.draftName = e.target.value; saveDraft(); });
  $("#scenario-notes").addEventListener("input", (e) => { state.notes = e.target.value; saveDraft(); });

  $("#recalc").addEventListener("click", refresh);

  $("#normalise").addEventListener("click", () => {
    const total = sum(state.weights);
    if (!total) return;
    for (const name of names) state.weights[name] = (state.weights[name] || 0) / total;
    renderWeights();
    saveDraft();
    refresh();
  });

  $("#clear").addEventListener("click", () => {
    for (const name of names) state.weights[name] = 0;
    renderWeights();
    saveDraft();
  });

  $("#save").addEventListener("click", async () => {
    const name = $("#scenario-name").value.trim();
    if (!name) { alert("Bitte einen Namen für das Szenario eingeben."); return; }
    if (name === DRAFT) { alert(`"${DRAFT}" ist reserviert - bitte anders benennen.`); return; }
    try {
      await api("/api/scenario", {
        method: "POST",
        body: JSON.stringify({
          name, weights: state.weights, benchmarks: state.benchmarks,
          ter: state.ter, notes: state.notes, mode: state.mode,
        }),
      });
      state.compare.add(name);
      await reload();
      setBusy(false);
      $("#status").textContent = `"${name}" gespeichert.`;
      setTimeout(() => ($("#status").textContent = ""), 2500);
    } catch (error) {
      alert(`Speichern fehlgeschlagen: ${error.message}`);
    }
  });

  $$(".tabs button").forEach((button) =>
    button.addEventListener("click", () => {
      state.tab = button.dataset.tab;
      renderActiveTab();
    })
  );

  $("#theme").addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("saa-theme", next); } catch { /* ignore */ }
    renderActiveTab();
  });
  try {
    const theme = localStorage.getItem("saa-theme");
    if (theme) document.documentElement.setAttribute("data-theme", theme);
  } catch { /* ignore */ }

  await refresh();
}

init().catch((error) => {
  document.body.insertAdjacentHTML(
    "afterbegin",
    `<div class="notice bad" style="margin:16px">Start fehlgeschlagen: ${error.message}</div>`
  );
});

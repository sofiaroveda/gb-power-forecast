import { lineChart } from "./chart.js";
import { COLORS, NAMES, getJSON, gbp, gbp0, longDate, mw, shortDate, showError, ukTime } from "./common.js";

const REPO = "https://github.com/sofiaroveda/gb-power-forecast";

// Ticks every 3 hours on a one-day chart (clock-change days have 46 or 50 points)
function dayTicks(times) {
  return times.map((t, i) => ({ i, label: t })).filter((t) => t.label.endsWith(":00") && Number(t.label.slice(0, 2)) % 3 === 0);
}

function argExtreme(values, better) {
  let best = -1;
  values.forEach((v, i) => { if (v != null && (best < 0 || better(v, values[best]))) best = i; });
  return best;
}

function renderForecast(fc) {
  document.getElementById("fc-day").textContent = longDate(fc.day);
  const before = new Date(`${fc.day}T12:00:00Z`);
  before.setUTCDate(before.getUTCDate() - 1);
  document.getElementById("fc-cutoff").textContent =
    `${ukTime(fc.cutoff)} UK time on ${longDate(before.toISOString().slice(0, 10), { year: false })}`;

  const vals = fc.model;
  const ok = vals.filter((v) => v != null);
  const hi = argExtreme(vals, (a, b) => a > b), lo = argExtreme(vals, (a, b) => a < b);
  document.getElementById("fc-avg").textContent = gbp0(ok.reduce((a, b) => a + b, 0) / ok.length);
  document.getElementById("fc-high").textContent = gbp0(vals[hi]);
  document.getElementById("fc-high-at").textContent = `at ${fc.time[hi]}`;
  document.getElementById("fc-low").textContent = gbp0(vals[lo]);
  document.getElementById("fc-low-at").textContent = `at ${fc.time[lo]}`;

  const keys = ["model", "naive_2d", "mean_7d"];
  lineChart(document.getElementById("fc-chart"), {
    title: `Forecast price for each half-hour of ${fc.day}`,
    labels: fc.time.map((t) => `${t} UK time`),
    series: keys.map((k) => ({ name: NAMES[k], values: fc[k], color: COLORS[k], width: k === "model" ? 2.5 : 2 })),
    xTicks: dayTicks(fc.time),
    format: gbp0,
  });

  const rows = fc.time.map((t, i) =>
    `<tr><td>${t}</td>${keys.map((k) => `<td>${gbp(fc[k][i])}</td>`).join("")}<td>${mw(fc.demand_fc[i])}</td><td>${mw(fc.wind_fc[i])}</td></tr>`);
  document.getElementById("fc-table").innerHTML =
    `<thead><tr><th>UK time</th>${keys.map((k) => `<th>${NAMES[k]}</th>`).join("")}<th>Demand forecast</th><th>Wind forecast</th></tr></thead><tbody>${rows.join("")}</tbody>`;

  lineChart(document.getElementById("drivers-chart"), {
    title: "Demand and wind forecasts used for this forecast",
    labels: fc.time.map((t) => `${t} UK time`),
    series: [
      { name: "Demand forecast", values: fc.demand_fc, color: COLORS.demand },
      { name: "Wind forecast", values: fc.wind_fc, color: COLORS.wind },
    ],
    xTicks: dayTicks(fc.time),
    format: mw,
    includeZero: true,
  });
  const missing = fc.demand_fc.filter((v) => v == null).length;
  const note = document.getElementById("drivers-note");
  note.textContent = missing > fc.time.length / 2
    ? `In winter the half-hourly demand forecast for most of the next day is published at 08:45 UTC, after the cutoff, so the model has it for only ${fc.time.length - missing} of ${fc.time.length} half-hours. It also uses the forecast daily peak (${mw(fc.peak_demand_fc)}), published two days ahead.`
    : `The forecast daily peak demand is ${mw(fc.peak_demand_fc)}.`;
}

function renderRecent(recent) {
  const days = recent.days;
  if (!days.length) return;
  const cat = (k) => days.flatMap((d) => d[k]);
  const labels = days.flatMap((d) => d.time.map((t) => `${shortDate(d.day)}, ${t}`));
  const ticks = [];
  let i = 0;
  for (const d of days) { ticks.push({ i, label: shortDate(d.day).split(" ").slice(0, 2).join(" ") }); i += d.time.length; }
  document.getElementById("recent-range").textContent =
    `${longDate(days[0].day, { weekday: false, year: false })} to ${longDate(days[days.length - 1].day, { weekday: false, year: false })}`;
  lineChart(document.getElementById("recent-chart"), {
    title: "Actual price and the model's forecast over the last 14 days",
    labels,
    series: [
      { name: NAMES.price, values: cat("price"), color: COLORS.price },
      { name: NAMES.model, values: cat("model"), color: COLORS.model },
    ],
    xTicks: ticks,
    format: gbp0,
  });

  const keys = ["model", "naive_2d", "mean_7d"];
  const body = days.slice().reverse().map((d) => {
    const best = Math.min(...keys.map((k) => d.mae[k]));
    return `<tr><td>${shortDate(d.day)}</td>${keys.map((k) => `<td class="${d.mae[k] === best ? "best" : ""}">${gbp(d.mae[k])}</td>`).join("")}</tr>`;
  });
  document.getElementById("recent-table").innerHTML =
    `<thead><tr><th>Day</th>${keys.map((k) => `<th>${NAMES[k]}</th>`).join("")}</tr></thead><tbody>${body.join("")}</tbody>`;
}

function renderRecord(rec) {
  const box = document.getElementById("record");
  if (!rec.first_day) {
    box.innerHTML = `<p>No live forecast has been saved yet.</p>`;
    return;
  }
  const start = `<p>The record starts with the forecast for ${longDate(rec.first_day)}. Each forecast is saved to the <a href="${REPO}/tree/main/forecasts">forecasts folder</a> after its 08:00 UTC cutoff and before its day starts, and a check stops anyone changing a saved forecast later. GitHub's history shows when each one was added.</p>`;
  if (!rec.totals) {
    box.innerHTML = `${start}<p>The first day is not over yet, so there is nothing to score.</p>`;
    return;
  }
  const t = rec.totals;
  const skill = 1 - t.mae_model / t.mae_naive_2d;
  const rows = rec.days.slice().reverse().map((d) => d.complete
    ? `<tr><td>${shortDate(d.day)}</td><td>${gbp(d.mae_model)}</td><td>${gbp(d.mae_naive_2d)}</td></tr>`
    : `<tr><td>${shortDate(d.day)}</td><td colspan="2" class="muted">Waiting for prices</td></tr>`);
  box.innerHTML = `${start}
    <div class="tiles">
      <div class="tile"><div class="tile-label">Days scored</div><div class="tile-value">${t.days}</div></div>
      <div class="tile"><div class="tile-label">Model average error</div><div class="tile-value">${gbp(t.mae_model)}</div></div>
      <div class="tile"><div class="tile-label">Two-days-earlier average error</div><div class="tile-value">${gbp(t.mae_naive_2d)}</div></div>
      <div class="tile"><div class="tile-label">Improvement</div><div class="tile-value">${Math.round(skill * 100)}%</div></div>
    </div>
    <div class="table-scroll"><table><thead><tr><th>Day</th><th>Model error</th><th>Two days earlier error</th></tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
}

Promise.all([getJSON("forecast.json"), getJSON("recent.json"), getJSON("record.json")])
  .then(([fc, recent, rec]) => { renderForecast(fc); renderRecent(recent); renderRecord(rec); })
  .catch(showError);

import { columnChart } from "./chart.js";
import { COLORS, NAMES, getJSON, gbp, gbp0, longDate, pct, showError } from "./common.js";

function renderBacktest(bt) {
  document.getElementById("bt-range").textContent =
    `${longDate(bt.first_day, { weekday: false })} to ${longDate(bt.last_day, { weekday: false })}`;
  document.getElementById("bt-days").textContent = bt.days.toLocaleString("en-GB");
  document.getElementById("bt-n").textContent = bt.half_hours.toLocaleString("en-GB");

  const order = ["naive_2d", "naive_7d", "mean_7d", "model"];
  document.getElementById("bt-table").innerHTML =
    `<thead><tr><th>Forecast</th><th>Average error (MAE)</th><th>RMSE</th><th>Improvement on two days earlier</th></tr></thead><tbody>` +
    order.map((k) => {
      const s = bt.scores[k];
      return `<tr class="${k === "model" ? "highlight" : ""}"><td>${NAMES[k]}</td><td>${gbp(s.mae)}</td><td>${gbp(s.rmse)}</td><td>${pct(s.skill)}</td></tr>`;
    }).join("") + `</tbody>`;

  const m = bt.scores.model, b = bt.scores.mean_7d;
  document.getElementById("bt-vs-best").textContent = pct(1 - m.mae / b.mae);

  const keys = ["model", "mean_7d", "naive_2d"];
  columnChart(document.getElementById("quarter-chart"), {
    title: "Average error by quarter",
    groups: bt.quarters.map((q) => q.quarter),
    short: (g) => g.replace(/^20(\d\d) /, "$1 "),
    series: keys.map((k) => ({ name: NAMES[k], values: bt.quarters.map((q) => q.mae[k]), color: COLORS[k] })),
    format: gbp0,
  });
  const wins = bt.quarters.filter((q) => keys.every((k) => q.mae.model <= q.mae[k])).length;
  document.getElementById("quarter-wins").textContent =
    wins === bt.quarters.length
      ? `The model had the lowest error in all ${wins} full quarters.`
      : `The model had the lowest error in ${wins} of ${bt.quarters.length} full quarters.`;
  document.getElementById("quarter-table").innerHTML =
    `<thead><tr><th>Quarter</th><th>Days</th>${keys.map((k) => `<th>${NAMES[k]}</th>`).join("")}</tr></thead><tbody>` +
    bt.quarters.map((q) => `<tr><td>${q.quarter}</td><td>${q.days}</td>${keys.map((k) => `<td>${gbp(q.mae[k])}</td>`).join("")}</tr>`).join("") +
    `</tbody>`;
}

function renderAblation(ab) {
  document.getElementById("ablation-range").textContent =
    `${longDate(ab.first_day, { weekday: false })} to ${longDate(ab.last_day, { weekday: false })}`;
  document.getElementById("ablation-table").innerHTML =
    `<thead><tr><th>Inputs</th><th>Average error (MAE)</th><th>Improvement on two days earlier</th></tr></thead><tbody>` +
    ab.runs.map((r) => `<tr class="${r.placebo ? "muted" : ""}"><td>${r.label}</td><td>${gbp(r.mae)}</td><td>${pct(r.skill)}</td></tr>`).join("") +
    `</tbody>`;
}

Promise.all([getJSON("backtest.json"), getJSON("ablation.json")])
  .then(([bt, ab]) => { renderBacktest(bt); renderAblation(ab); })
  .catch(showError);

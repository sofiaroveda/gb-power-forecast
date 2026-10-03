// Helpers shared by every page.

export async function getJSON(name) {
  const res = await fetch(`data/${name}`, { cache: "no-cache" });
  if (!res.ok) throw new Error(`Could not load ${name}`);
  return res.json();
}

export const NAMES = {
  model: "Model",
  naive_2d: "Same time two days earlier",
  naive_7d: "Same time a week earlier",
  mean_7d: "7-day average",
  price: "Actual price",
};

// Each forecaster keeps one colour on every chart
export const COLORS = {
  model: "--s-model",
  naive_2d: "--s-naive",
  mean_7d: "--s-mean",
  price: "--s-actual",
  demand: "--s-demand",
  wind: "--s-wind",
};

const sign = (v) => (v < 0 ? "-" : "");
export const gbp = (v) => (v == null ? "–" : `${sign(v)}£${Math.abs(v).toFixed(2)}`);
export const gbp0 = (v) => (v == null ? "–" : `${sign(Math.round(v))}£${Math.abs(Math.round(v))}`);
export const mw = (v) => (v == null ? "–" : `${(v / 1000).toFixed(1)} GW`);
export const pct = (v) => `${Math.round(v * 100)}%`;

// "2026-10-04" -> "Sunday 4 October 2026"
export function longDate(iso, { weekday = true, year = true } = {}) {
  const d = new Date(`${iso}T12:00:00Z`);
  return d.toLocaleDateString("en-GB", {
    weekday: weekday ? "long" : undefined, day: "numeric", month: "long",
    year: year ? "numeric" : undefined, timeZone: "UTC",
  }).replace(",", "");
}

export function shortDate(iso) {
  const d = new Date(`${iso}T12:00:00Z`);
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
}

// Time in UK clock time, e.g. "08:00 UK time" from an ISO timestamp
export function ukTime(iso) {
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/London" });
}

export function showError(err) {
  const main = document.querySelector("main");
  const box = document.createElement("p");
  box.className = "error";
  box.textContent = `Sorry, the data could not be loaded (${err.message}).`;
  main.prepend(box);
}

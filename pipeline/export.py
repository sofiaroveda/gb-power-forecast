"""Make the live forecast and write the data files the website reads.

    python -m pipeline.export

The forecast for the next delivery day comes from exactly the procedure the
backtest scores: the delivery day's half-hours are added with no price, the
features use only what was public at its cutoff, and model.walk_forward makes
the prediction. If the cutoff has passed and the day has not started, the
forecast is also saved to the prediction record (pipeline/ledger.py).

Writes site/data/forecast.json, recent.json, backtest.json and record.json.
"""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from pipeline import evaluate, features, ledger, model
from pipeline.data import load

SITE_DATA = Path(__file__).resolve().parent.parent / "site" / "data"
RECENT_DAYS = 14


def cutoff_for(day: date) -> pd.Timestamp:
    """08:00 UTC on the day before delivery."""
    return pd.Timestamp(day - timedelta(days=1), tz="UTC") + pd.Timedelta(
        hours=features.CUTOFF_HOUR_UTC)


def periods_in(day: date) -> int:
    """46, 48 or 50 half-hours, depending on clock changes."""
    length = ledger.day_start(day + timedelta(days=1)) - ledger.day_start(day)
    return int(length / features.PERIOD)


def target_day(now: pd.Timestamp) -> date:
    """The day to forecast: tomorrow once today's cutoff has passed, otherwise
    today (whose cutoff was yesterday morning). Days are UK days."""
    today = now.tz_convert(features.UK).date()
    tomorrow = today + timedelta(days=1)
    return tomorrow if now >= cutoff_for(tomorrow) else today


def _clean(x):
    """Numbers rounded for the site; NaN becomes null in the JSON."""
    if isinstance(x, float):
        return None if math.isnan(x) else round(x, 2)
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_clean(v) for v in x]
    return x


def _write(name: str, data: dict) -> None:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / name).write_text(json.dumps(_clean(data), indent=1) + "\n")


def _uk_time(t: pd.Series) -> list[str]:
    return t.dt.tz_convert(features.UK).dt.strftime("%H:%M").tolist()


def forecast_json(df: pd.DataFrame, day: date, now: pd.Timestamp) -> dict:
    d = df[df["delivery_date"] == day]
    peak = d["demand_peak_fc"].dropna()
    priced = df.loc[df["price"].notna(), "start_time"]
    return {
        "day": str(day),
        "cutoff": cutoff_for(day).isoformat(),
        "made_at": now.floor("min").isoformat(),
        # the newest half-hour price Elexon had published when this run downloaded,
        # to check features.PRICE_DELAY is long enough
        "last_price_available": priced.max().isoformat() if len(priced) else None,
        "peak_demand_fc": float(peak.iloc[0]) if len(peak) else None,
        "time": _uk_time(d["start_time"]),
        "start_time": d["start_time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ").tolist(),
        **{c: d[c].astype(float).tolist() for c in
           ["model", "naive_2d", "naive_7d", "mean_7d", "demand_fc", "wind_fc"]},
    }


def recent_json(df: pd.DataFrame, days: int = RECENT_DAYS) -> dict:
    """The last `days` delivery days with a price and a model forecast for every
    half-hour (a baseline can be missing where its earlier price was)."""
    scored = df.dropna(subset=["price", "model"])
    counts = scored.groupby("delivery_date").size()
    complete = [d for d in counts.index if counts[d] == periods_in(d)][-days:]
    out = []
    for day in complete:
        d = scored[scored["delivery_date"] == day]
        out.append({
            "day": str(day),
            "time": _uk_time(d["start_time"]),
            "price": d["price"].tolist(),
            **{f: d[f].tolist() for f in evaluate.FORECASTERS},
            # each day's errors on the half-hours where every forecaster exists
            "mae": {f: float((c[f] - c["price"]).abs().mean())
                    for c in [d.dropna(subset=evaluate.FORECASTERS)] for f in evaluate.FORECASTERS},
        })
    return {"days": out}


def backtest_json(df: pd.DataFrame) -> dict:
    scored = evaluate.common_rows(df)
    s = evaluate.scores(df)
    q = scored.assign(quarter=pd.to_datetime(scored["delivery_date"]).dt.to_period("Q"))
    quarters = []
    for quarter, g in q.groupby("quarter"):
        if g["delivery_date"].nunique() < 28:
            continue  # a quarter that has only just started is too short to compare
        mae = {f: float((g[f] - g["price"]).abs().mean()) for f in evaluate.FORECASTERS}
        quarters.append({"quarter": f"{quarter.year} Q{quarter.quarter}",
                         "days": int(g["delivery_date"].nunique()), "mae": mae})
    return {
        "first_day": str(scored["delivery_date"].min()),
        "last_day": str(scored["delivery_date"].max()),
        "days": int(scored["delivery_date"].nunique()),
        "half_hours": len(scored),
        "scores": {f: {"mae": float(s.loc[f, "mae"]), "rmse": float(s.loc[f, "rmse"]),
                       "skill": float(s.loc[f, "skill_vs_naive_2d"])}
                   for f in evaluate.FORECASTERS},
        "quarters": quarters,
    }


def record_json(prices: pd.DataFrame, folder: Path | None = None) -> dict:
    """The saved live forecasts, scored once their day's prices are in."""
    rec = ledger.load_all(folder)
    if rec.empty:
        return {"first_day": None, "days": [], "totals": None}
    rec = rec.merge(prices[["start_time", "price"]], on="start_time", how="left")
    days = []
    for day, g in rec.groupby("delivery_date"):
        priced = g.dropna(subset=["price", "model", "naive_2d"])
        complete = len(priced) == len(g)
        days.append({
            "day": str(day), "complete": complete,
            "mae_model": float((priced["model"] - priced["price"]).abs().mean()) if complete else None,
            "mae_naive_2d": float((priced["naive_2d"] - priced["price"]).abs().mean()) if complete else None,
        })
    done = [d["day"] for d in days if d["complete"]]
    scored = rec[rec["delivery_date"].astype(str).isin(done)]
    totals = None
    if done:
        totals = {"days": len(done), "half_hours": len(scored),
                  "mae_model": float((scored["model"] - scored["price"]).abs().mean()),
                  "mae_naive_2d": float((scored["naive_2d"] - scored["price"]).abs().mean())}
    return {"first_day": days[0]["day"], "days": days, "totals": totals}


def run(now: pd.Timestamp | None = None) -> date:
    now = now or pd.Timestamp.now(tz="UTC")
    prices = load("prices")
    day = target_day(now)
    df = features.build(features.add_day(prices, day), load("demand_forecast"),
                        load("wind_forecast"), load("peak_forecast"))
    df = model.walk_forward(df)

    saved = ledger.record(df[df["delivery_date"] == day], day, cutoff_for(day), now)
    _write("forecast.json", forecast_json(df, day, now))
    _write("recent.json", recent_json(df))
    _write("backtest.json", backtest_json(df))
    _write("record.json", record_json(prices))
    print(f"Forecast for {day} written" + (f", saved to {saved.name}" if saved else ""))
    return day


if __name__ == "__main__":
    run()

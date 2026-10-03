"""Synthetic data shaped like the Elexon API output.

Each day has a demand and wind forecast published before the cutoff, and a
second, more accurate one published after it. The later one would help a
forecaster that cheats, so tests can check it is never used.
"""

import numpy as np
import pandas as pd
import pytest


def make_synthetic(days: int = 200, seed: int = 1, start: str = "2025-01-01"):
    rng = np.random.default_rng(seed)
    t = pd.date_range(start, periods=days * 48, freq="30min", tz="UTC")
    hour = t.hour + t.minute / 60
    demand_true = 25000 + 6000 * np.sin((hour - 6) / 24 * 2 * np.pi) + rng.normal(0, 800, len(t))
    wind_daily = rng.uniform(1000, 15000, days).repeat(48)
    wind_true = np.clip(wind_daily + rng.normal(0, 1500, len(t)), 0, None)
    price = 20 + 0.006 * (demand_true - wind_true) + rng.normal(0, 8, len(t))
    prices = pd.DataFrame({"start_time": t, "price": price, "volume": 1000.0})

    # forecasts: an early, noisy publish (before cutoff) and a late, exact one (after)
    day_start = t.floor("D")
    early = day_start - pd.Timedelta(days=1) + pd.Timedelta(hours=7, minutes=45)
    late = day_start - pd.Timedelta(days=1) + pd.Timedelta(hours=10)
    demand = pd.concat([
        pd.DataFrame({"publish_time": early, "start_time": t,
                      "value": demand_true + rng.normal(0, 1500, len(t))}),
        pd.DataFrame({"publish_time": late, "start_time": t, "value": demand_true}),
    ], ignore_index=True)
    hourly = t[t.minute == 0]
    w_true = pd.Series(wind_true, index=t).reindex(hourly).values
    hday = hourly.floor("D")
    wind = pd.concat([
        pd.DataFrame({"publish_time": hday - pd.Timedelta(days=1) + pd.Timedelta(hours=5, minutes=30),
                      "start_time": hourly, "value": w_true + rng.normal(0, 2500, len(hourly))}),
        pd.DataFrame({"publish_time": hday - pd.Timedelta(days=1) + pd.Timedelta(hours=12),
                      "start_time": hourly, "value": w_true}),
    ], ignore_index=True)
    # daily peak forecast for each date: published on D-2 at 14:45 (allowed)
    # and again, exactly, on D-1 at 10:00 (after the cutoff, never to be used)
    dates = pd.Series(t.floor("D").unique())
    peak_true = pd.Series(demand_true, index=t).resample("D").max().values
    peak = pd.concat([
        pd.DataFrame({"publish_time": dates - pd.Timedelta(days=2) + pd.Timedelta(hours=14, minutes=45),
                      "forecast_date": dates.dt.date,
                      "value": peak_true + rng.normal(0, 1500, len(dates))}),
        pd.DataFrame({"publish_time": dates - pd.Timedelta(days=1) + pd.Timedelta(hours=10),
                      "forecast_date": dates.dt.date, "value": peak_true}),
    ], ignore_index=True)
    return prices, demand, wind, peak


@pytest.fixture(scope="session")
def synthetic():
    return make_synthetic()

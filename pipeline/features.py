"""Turn raw prices and forecasts into one row per half-hour, using only what
was known at the forecast cutoff.

The setting: on the morning of day D-1 we forecast every half-hour of day D.
The cutoff is 08:00 UTC on D-1 (08:00 or 09:00 UK time), before the morning
day-ahead auction. Anything published or realised after the cutoff is not
allowed into the features for day D. tests/test_no_lookahead.py checks this.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

UK = "Europe/London"
CUTOFF_HOUR_UTC = 8
FEATURES = [
    "demand_fc", "demand_peak_fc", "wind_fc", "residual_fc", "wind_share_fc",
    "hour", "dow", "month", "weekend",
    "lag_2d", "lag_7d", "mean_same_period_7d", "mean_last_24h",
]


def delivery_frame(prices: pd.DataFrame) -> pd.DataFrame:
    """One row per half-hour with its UK delivery date and forecast cutoff."""
    df = prices[["start_time", "price"]].copy().sort_values("start_time")
    local = df["start_time"].dt.tz_convert(UK)
    df["delivery_date"] = local.dt.date
    d = pd.to_datetime(df["delivery_date"]).dt.tz_localize("UTC")
    df["cutoff"] = d - pd.Timedelta(days=1) + pd.Timedelta(hours=CUTOFF_HOUR_UTC)
    df["hour"] = local.dt.hour + local.dt.minute / 60
    df["dow"] = local.dt.dayofweek
    df["month"] = local.dt.month
    df["weekend"] = (df["dow"] >= 5).astype(int)
    return df.reset_index(drop=True)


def latest_before_cutoff(fc: pd.DataFrame, rows: pd.DataFrame, hourly: bool = False) -> pd.Series:
    """For each row, the most recent forecast for that time published at or
    before the row's cutoff. Hourly forecasts (wind) cover both half-hours."""
    key = rows["start_time"].dt.floor("h") if hourly else rows["start_time"]
    left = pd.DataFrame({"row": rows.index, "key": key, "cutoff": rows["cutoff"]})
    right = fc.rename(columns={"start_time": "key"})[["key", "publish_time", "value"]]
    m = left.merge(right, on="key", how="left")
    m = m[m["publish_time"] <= m["cutoff"]]
    m = m.sort_values("publish_time").groupby("row").tail(1)
    return m.set_index("row")["value"].reindex(rows.index)


def peak_before_cutoff(peak: pd.DataFrame, rows: pd.DataFrame) -> pd.Series:
    """For each row, the latest daily peak demand forecast for its delivery date
    published at or before the row's cutoff."""
    left = pd.DataFrame({"row": rows.index, "forecast_date": rows["delivery_date"],
                         "cutoff": rows["cutoff"]})
    m = left.merge(peak[["forecast_date", "publish_time", "value"]], on="forecast_date", how="left")
    m = m[m["publish_time"] <= m["cutoff"]]
    m = m.sort_values("publish_time").groupby("row").tail(1)
    return m.set_index("row")["value"].reindex(rows.index)


def price_lags(rows: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    s = prices.set_index("start_time")["price"].sort_index()
    t = rows["start_time"]
    out = pd.DataFrame(index=rows.index)
    out["lag_2d"] = s.reindex(t - pd.Timedelta(days=2)).values
    out["lag_7d"] = s.reindex(t - pd.Timedelta(days=7)).values
    same = np.column_stack([s.reindex(t - pd.Timedelta(days=k)).values for k in range(2, 9)])
    counts = np.isfinite(same).sum(axis=1)
    sums = np.nansum(same, axis=1)
    out["mean_same_period_7d"] = np.where(counts > 0, sums / np.maximum(counts, 1), np.nan)
    # mean price over the 24 hours before the cutoff (all realised by then)
    roll = s.rolling("24h").mean()
    last_known = rows["cutoff"] - pd.Timedelta(minutes=30)
    uniq = pd.DatetimeIndex(last_known.unique())
    at_cutoff = roll.reindex(roll.index.union(uniq)).ffill().reindex(uniq)
    out["mean_last_24h"] = last_known.map(at_cutoff).values
    return out


def build(prices: pd.DataFrame, demand_fc: pd.DataFrame, wind_fc: pd.DataFrame,
          peak_fc: pd.DataFrame) -> pd.DataFrame:
    rows = delivery_frame(prices)
    # In winter the half-hourly NDF for most of tomorrow is published after the
    # cutoff, so demand_fc is often missing; the daily peak forecast is not.
    rows["demand_fc"] = latest_before_cutoff(demand_fc, rows)
    rows["demand_peak_fc"] = peak_before_cutoff(peak_fc, rows)
    rows["wind_fc"] = latest_before_cutoff(wind_fc, rows, hourly=True)
    rows["residual_fc"] = rows["demand_fc"] - rows["wind_fc"]
    rows["wind_share_fc"] = rows["wind_fc"] / rows["demand_fc"]
    rows = pd.concat([rows, price_lags(rows, prices)], axis=1)
    return rows

"""Score every forecaster on the same half-hours.

MAE and RMSE are in pounds per MWh. Skill compares a forecaster with the
naive_2d baseline: 0% means no better than copying the price from two days
earlier, 100% would mean a perfect forecast.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FORECASTERS = ["naive_2d", "naive_7d", "mean_7d", "model"]


def finished(df: pd.DataFrame) -> pd.DataFrame:
    """Drop delivery days that are not over yet (today, while the data runs up to now)."""
    if "start_time" not in df:
        return df
    last_end = df.loc[df["price"].notna(), "start_time"].max() + pd.Timedelta(minutes=30)
    next_day = pd.to_datetime(df["delivery_date"]) + pd.Timedelta(days=1)
    day_end = next_day.dt.tz_localize("Europe/London").dt.tz_convert("UTC")
    return df[(day_end <= last_end).to_numpy()]


def common_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Only half-hours of finished days where every forecaster and the actual price exist."""
    return finished(df).dropna(subset=["price", *FORECASTERS])


def scores(df: pd.DataFrame) -> pd.DataFrame:
    d = common_rows(df)
    out = []
    base_mae = (d["naive_2d"] - d["price"]).abs().mean()
    for f in FORECASTERS:
        err = d[f] - d["price"]
        mae = err.abs().mean()
        out.append({
            "forecaster": f,
            "mae": mae,
            "rmse": float(np.sqrt((err ** 2).mean())),
            "skill_vs_naive_2d": 1 - mae / base_mae,
        })
    return pd.DataFrame(out).set_index("forecaster")


def by_month(df: pd.DataFrame) -> pd.DataFrame:
    d = common_rows(df).copy()
    d["month"] = pd.to_datetime(d["delivery_date"]).dt.to_period("M").astype(str)
    return d.groupby("month").apply(
        lambda g: pd.Series({f: (g[f] - g["price"]).abs().mean() for f in FORECASTERS}),
        include_groups=False)

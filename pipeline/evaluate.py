"""Score every forecaster on the same half-hours.

MAE and RMSE are in pounds per MWh. Skill compares a forecaster with the
naive_2d baseline: 0% means no better than copying the price from two days
earlier, 100% would mean a perfect forecast.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FORECASTERS = ["naive_2d", "naive_7d", "mean_7d", "model"]


def common_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Only half-hours where every forecaster and the actual price exist."""
    return df.dropna(subset=["price", *FORECASTERS])


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

"""Forecasters and the walk-forward backtest.

Baselines (no fitting):
- naive_2d: the same half-hour two days earlier (the latest full day known at the cutoff)
- naive_7d: the same half-hour a week earlier
- mean_7d:  the average of that half-hour over the seven most recent known days

Model: gradient-boosted trees on the demand and wind forecasts, calendar and
recent prices. It is refitted at the start of every month using only rows whose
prices were realised before that month's first cutoff, so it never trains on the
future.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from pipeline.features import FEATURES

BASELINES = {"naive_2d": "lag_2d", "naive_7d": "lag_7d", "mean_7d": "mean_same_period_7d"}


def make_model(seed: int = 0) -> HistGradientBoostingRegressor:
    # absolute error loss: prices have big spikes, and we score on MAE
    return HistGradientBoostingRegressor(
        loss="absolute_error", max_iter=300, learning_rate=0.05,
        max_leaf_nodes=31, min_samples_leaf=40, random_state=seed)


def walk_forward(df: pd.DataFrame, min_train_days: int = 90, seed: int = 0) -> pd.DataFrame:
    """Return a copy of df with a 'model' column of out-of-sample predictions."""
    df = df.sort_values("start_time").reset_index(drop=True).copy()
    df["model"] = np.nan
    months = pd.to_datetime(df["delivery_date"]).dt.to_period("M")
    first_date = pd.to_datetime(df["delivery_date"]).min()
    for month in months.unique():
        test = months == month
        cutoff = df.loc[test, "cutoff"].min()
        # a half-hour's price is known once it has finished
        train = (df["start_time"] + pd.Timedelta(minutes=30) <= cutoff) & df["price"].notna()
        if (pd.Timestamp(month.start_time) - first_date).days < min_train_days or train.sum() < 1000:
            continue
        model = make_model(seed).fit(df.loc[train, FEATURES], df.loc[train, "price"])
        df.loc[test, "model"] = model.predict(df.loc[test, FEATURES])
    for name, col in BASELINES.items():
        df[name] = df[col]
    return df

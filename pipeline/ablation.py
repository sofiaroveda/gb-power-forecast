"""Which inputs does the model's accuracy come from?

    python -m pipeline.ablation

Re-runs the walk-forward backtest with groups of inputs left out, plus a
placebo that adds information the model must not have (the previous day's
actual prices, mostly unknown at the 08:00 cutoff). If the honest model were
already as good as the placebo, it would suggest a leak somewhere.

Run by hand (it takes a few minutes), not by the daily update. Writes
site/data/ablation.json.
"""

from __future__ import annotations

import json

import pandas as pd

from pipeline import evaluate, features, model
from pipeline.data import load
from pipeline.export import SITE_DATA, _clean

CALENDAR = ["hour", "dow", "month", "weekend"]
LAGS = ["lag_2d", "lag_7d", "mean_same_period_7d", "mean_last_24h"]
FUNDAMENTALS = ["demand_fc", "demand_peak_fc", "wind_fc", "residual_fc", "wind_share_fc"]

RUNS = [
    ("All inputs (the model)", features.FEATURES, False),
    ("Without recent prices", CALENDAR + FUNDAMENTALS, False),
    ("Without demand and wind forecasts", CALENDAR + LAGS, False),
    ("Recent prices and wind forecast only", CALENDAR + LAGS + ["wind_fc"], False),
    ("Placebo: all inputs plus the previous day's actual prices", features.FEATURES + ["leak_1d"], True),
]


def run() -> dict:
    df = features.build(load("prices"), load("demand_forecast"), load("wind_forecast"),
                        load("peak_forecast"))
    s = df.set_index("start_time")["price"]
    df["leak_1d"] = s.reindex(df["start_time"] - pd.Timedelta(days=1)).values

    reference = None
    results = []
    original = model.FEATURES
    try:
        for label, cols, placebo in RUNS:
            model.FEATURES = cols
            out = model.walk_forward(df)
            if reference is None:
                reference = evaluate.common_rows(out).index
            d = out.loc[reference]  # every run scored on the same half-hours
            mae = (d["model"] - d["price"]).abs().mean()
            base = (d["naive_2d"] - d["price"]).abs().mean()
            results.append({"label": label, "mae": float(mae), "skill": float(1 - mae / base),
                            "placebo": placebo})
            print(f"{label:60s} MAE {mae:6.2f}  skill {1 - mae / base:.3f}")
    finally:
        model.FEATURES = original
    d = df.loc[reference]
    data = {"first_day": str(d["delivery_date"].min()), "last_day": str(d["delivery_date"].max()),
            "half_hours": len(reference), "runs": results}
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "ablation.json").write_text(json.dumps(_clean(data), indent=1) + "\n")
    return data


if __name__ == "__main__":
    run()

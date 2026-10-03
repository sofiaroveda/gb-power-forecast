"""Run the full walk-forward backtest on the downloaded data.

    python -m pipeline.backtest

Writes results/predictions.csv, results/scores.csv and results/monthly_mae.csv,
and prints the headline table.
"""

from __future__ import annotations

from pathlib import Path

from pipeline import evaluate, features, model
from pipeline.data import load

RESULTS = Path(__file__).resolve().parent.parent / "results"


def run():
    df = features.build(load("prices"), load("demand_forecast"), load("wind_forecast"),
                        load("peak_forecast"))
    df = model.walk_forward(df)
    RESULTS.mkdir(exist_ok=True)
    cols = ["start_time", "delivery_date", "price", *evaluate.FORECASTERS]
    df[cols].to_csv(RESULTS / "predictions.csv", index=False)
    s = evaluate.scores(df)
    s.to_csv(RESULTS / "scores.csv")
    evaluate.by_month(df).to_csv(RESULTS / "monthly_mae.csv")
    n = len(evaluate.common_rows(df))
    print(f"Scored on {n:,} half-hours\n")
    print(s.round({"mae": 2, "rmse": 2, "skill_vs_naive_2d": 3}).to_string())
    return s


if __name__ == "__main__":
    run()

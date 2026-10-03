"""Download prices and forecasts and save them as CSV files in data/.

    python -m pipeline.data                      # 2023-01-01 to now
    python -m pipeline.data --start 2024-01-01   # shorter history, quicker

By default the download runs up to now: today's prices so far and this
morning's forecasts are needed for tomorrow's live forecast.

The first full run makes roughly 2,500 small requests and takes a while;
after that, cached chunks in data/raw/ make re-runs fast.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from pipeline import api

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load(name: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / f"{name}.csv")
    for col in ("start_time", "publish_time"):
        if col in df:
            df[col] = pd.to_datetime(df[col], utc=True)
    if "forecast_date" in df:
        df["forecast_date"] = pd.to_datetime(df["forecast_date"]).dt.date
    return df


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2023-01-01")
    # end is exclusive, so the default (tomorrow, UK time) includes today so far
    tomorrow = pd.Timestamp.now(tz="Europe/London").date() + timedelta(days=1)
    p.add_argument("--end", default=str(tomorrow))
    args = p.parse_args(argv)
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)

    DATA_DIR.mkdir(exist_ok=True)
    print(f"Prices {start} to {end} ...")
    api.download_prices(start, end).to_csv(DATA_DIR / "prices.csv", index=False)
    print("Demand forecasts (NDF) ...")
    api.download_forecasts("NDF", "demand", start, end).to_csv(
        DATA_DIR / "demand_forecast.csv", index=False)
    print("Wind forecasts (WINDFOR) ...")
    api.download_forecasts("WINDFOR", "generation", start, end).to_csv(
        DATA_DIR / "wind_forecast.csv", index=False)
    print("Daily peak demand forecasts (NDFD) ...")
    api.download_daily_peak(start, end).to_csv(DATA_DIR / "peak_forecast.csv", index=False)
    for name in ("prices", "demand_forecast", "wind_forecast", "peak_forecast"):
        print(f"  {name}: {len(load(name)):,} rows")


if __name__ == "__main__":
    main()

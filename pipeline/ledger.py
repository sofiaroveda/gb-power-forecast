"""A record of live forecasts that can be added to but never changed.

Each delivery day's forecast is saved to forecasts/YYYY-MM-DD.csv once its
08:00 UTC cutoff has passed and before the day starts. An existing file is
never rewritten, and pipeline/check.py fails if a later commit edits or
deletes one. GitHub's record of when each file was pushed shows the forecast
existed before the prices it forecast.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from pipeline.features import UK

FORECASTS_DIR = Path(__file__).resolve().parent.parent / "forecasts"
COLUMNS = ["start_time", "model", "naive_2d", "naive_7d", "mean_7d"]


def day_start(day: date) -> pd.Timestamp:
    """The first moment of a UK delivery day, in UTC."""
    return pd.Timestamp(day, tz=UK).tz_convert("UTC")


def path_for(day: date, folder: Path | None = None) -> Path:
    return (folder or FORECASTS_DIR) / f"{day}.csv"


def record(rows: pd.DataFrame, day: date, cutoff: pd.Timestamp, now: pd.Timestamp,
           folder: Path | None = None) -> Path | None:
    """Save the forecast for `day` if it is not saved yet, the cutoff has passed
    (so the inputs are final) and the day has not started. Returns the new file
    or None."""
    path = path_for(day, folder)
    if path.exists() or now < cutoff or now >= day_start(day):
        return None
    out = rows[COLUMNS].copy()
    out["start_time"] = out["start_time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    path.parent.mkdir(parents=True, exist_ok=True)
    out.round(2).to_csv(path, index=False)
    return path


def load_all(folder: Path | None = None) -> pd.DataFrame:
    """Every saved forecast, one row per half-hour, with its delivery day."""
    frames = []
    for path in sorted((folder or FORECASTS_DIR).glob("*.csv")):
        df = pd.read_csv(path, parse_dates=["start_time"])
        df["delivery_date"] = date.fromisoformat(path.stem)
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=[*COLUMNS, "delivery_date"])
    return pd.concat(frames, ignore_index=True)

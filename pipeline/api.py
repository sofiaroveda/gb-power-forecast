"""Download data from Elexon's Insights Solution API (free, no API key).

Three series are used:

- MID: the half-hourly Market Index price (APX provider), our target.
- NDF: National Demand Forecast, republished about every 30 minutes.
- WINDFOR: wind generation forecast, republished several times a day.
- NDFD: forecast daily peak demand for 2 to 14 days ahead, published once a
  day in the afternoon. It is a fallback for winter, when the half-hourly NDF
  covering tomorrow comes out at about 08:45 UTC, after the 08:00 cutoff.

The API limits how much one request can return (7 days for MID, 1 day of
publish times for NDF and WINDFOR), so requests are split into chunks.
Every chunk is cached in data/raw/ so a re-run only downloads what is missing.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

BASE = "https://data.elexon.co.uk/bmrs/api/v1"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%MZ")


def _get(url: str, params: dict, retries: int = 4) -> dict:
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed after {retries} attempts: {url} {params}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cached(name: str, fetch, window_end: datetime) -> dict:
    """Fetch once and keep the result, but only for windows that ended more than
    a day ago: recent windows can still gain rows, so they are fetched again."""
    path = RAW_DIR / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    data = fetch()
    if window_end <= _now() - timedelta(days=1):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
    return data


def chunks(start: datetime, end: datetime, step: timedelta):
    """Split [start, end) into consecutive windows no longer than step."""
    t = start
    while t < end:
        u = min(t + step, end)
        yield t, u
        t = u


# ---------- parsing (kept separate from downloading so it can be tested) ----------

def parse_mid(payload: dict) -> pd.DataFrame:
    """Market Index Data -> start_time, price, volume.

    Periods with zero traded volume are reported as price 0 and are not real
    prices, so they are set to missing.
    """
    rows = payload.get("data", [])
    df = pd.DataFrame(rows, columns=["startTime", "price", "volume"]) if rows else \
        pd.DataFrame(columns=["startTime", "price", "volume"])
    df = df.rename(columns={"startTime": "start_time"})
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
    df["price"] = pd.to_numeric(df["price"], errors="coerce").astype(float)
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype(float)
    df.loc[df["volume"] <= 0, "price"] = float("nan")
    return df[["start_time", "price", "volume"]]


def parse_forecast(payload: dict, value_key: str) -> pd.DataFrame:
    """NDF or WINDFOR dataset -> publish_time, start_time, value."""
    rows = payload.get("data", [])
    cols = ["publishTime", "startTime", value_key]
    df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)
    df = df.rename(columns={"publishTime": "publish_time", "startTime": "start_time",
                            value_key: "value"})
    df["publish_time"] = pd.to_datetime(df["publish_time"], utc=True)
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
    df["value"] = pd.to_numeric(df["value"], errors="coerce").astype(float)
    return df[["publish_time", "start_time", "value"]]


def parse_ndfd(payload: dict) -> pd.DataFrame:
    """NDFD dataset -> publish_time, forecast_date, value (daily peak demand, MW)."""
    rows = payload.get("data", [])
    cols = ["publishTime", "forecastDate", "demand"]
    df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)
    df = df.rename(columns={"publishTime": "publish_time", "forecastDate": "forecast_date",
                            "demand": "value"})
    df["publish_time"] = pd.to_datetime(df["publish_time"], utc=True)
    df["forecast_date"] = pd.to_datetime(df["forecast_date"]).dt.date
    df["value"] = pd.to_numeric(df["value"], errors="coerce").astype(float)
    return df[["publish_time", "forecast_date", "value"]]


# ---------- downloading ----------

def download_prices(start: date, end: date) -> pd.DataFrame:
    """Prices for every half-hour of the UK delivery days start to end - 1.

    UK days start at 23:00 UTC the evening before during British Summer Time,
    so the request begins a day early and is then trimmed to whole UK days.
    """
    s = datetime(start.year, start.month, start.day, tzinfo=timezone.utc) - timedelta(days=1)
    e = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
    frames = []
    for a, b in chunks(s, e, timedelta(days=7)):
        name = f"mid_{a:%Y%m%d}_{b:%Y%m%d}"
        payload = _cached(name, lambda a=a, b=b: _get(
            f"{BASE}/balancing/pricing/market-index",
            {"from": _iso(a), "to": _iso(b), "dataProviders": "APXMIDP", "format": "json"}), b)
        frames.append(parse_mid(payload))
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates("start_time").sort_values("start_time")
    uk_date = df["start_time"].dt.tz_convert("Europe/London").dt.date
    return df[(uk_date >= start) & (uk_date < end)].reset_index(drop=True)


def download_forecasts(dataset: str, value_key: str, start: date, end: date,
                       window_start_hour: int = 0, window_end_hour: int = 12) -> pd.DataFrame:
    """For each day in [start - 1 day, end), download the forecasts published
    between window_start_hour and window_end_hour UTC.

    Only the morning publishes are needed, because a forecast for day D must be
    made from what was published by the morning of D-1.
    """
    frames = []
    d = start - timedelta(days=1)
    while d < end:
        a = datetime(d.year, d.month, d.day, window_start_hour, tzinfo=timezone.utc)
        b = datetime(d.year, d.month, d.day, window_end_hour, tzinfo=timezone.utc)
        name = f"{dataset.lower()}_{a:%Y%m%d%H}_{b:%H}"
        payload = _cached(name, lambda a=a, b=b: _get(
            f"{BASE}/datasets/{dataset}",
            {"publishDateTimeFrom": _iso(a), "publishDateTimeTo": _iso(b), "format": "json"}), b)
        frames.append(parse_forecast(payload, value_key))
        d += timedelta(days=1)
    df = pd.concat(frames, ignore_index=True)
    return df.drop_duplicates(["publish_time", "start_time"]).sort_values(
        ["start_time", "publish_time"]).reset_index(drop=True)


def download_daily_peak(start: date, end: date) -> pd.DataFrame:
    """NDFD publishes from three days before start up to end, in 30-day requests."""
    s = datetime(start.year, start.month, start.day, tzinfo=timezone.utc) - timedelta(days=3)
    e = datetime(end.year, end.month, end.day, tzinfo=timezone.utc)
    frames = []
    for a, b in chunks(s, e, timedelta(days=30)):
        name = f"ndfd_{a:%Y%m%d}_{b:%Y%m%d}"
        payload = _cached(name, lambda a=a, b=b: _get(
            f"{BASE}/datasets/NDFD",
            {"publishDateTimeFrom": _iso(a), "publishDateTimeTo": _iso(b), "format": "json"}), b)
        frames.append(parse_ndfd(payload))
    df = pd.concat(frames, ignore_index=True)
    return df.drop_duplicates(["publish_time", "forecast_date"]).sort_values(
        ["forecast_date", "publish_time"]).reset_index(drop=True)

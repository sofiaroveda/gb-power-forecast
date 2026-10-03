"""Run the download functions against a fake API to check the chunking,
caching and de-duplication without touching the network."""

from datetime import date

import pandas as pd

from pipeline import api


def test_download_prices_and_forecasts(monkeypatch, tmp_path):
    calls = []

    def fake_get(url, params, retries=4):
        calls.append((url, params))
        if "market-index" in url:
            start = pd.Timestamp(params["from"])
            t = pd.date_range(start, periods=3, freq="30min")
            return {"data": [{"startTime": x.strftime("%Y-%m-%dT%H:%M:%SZ"), "price": 100.0,
                              "volume": 10.0} for x in t]}
        day = pd.Timestamp(params["publishDateTimeFrom"]).floor("D")
        start = (day + pd.Timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        key = "demand" if "NDF" in url else "generation"
        return {"data": [{"publishTime": (day + pd.Timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                          "startTime": start, key: 1234}]}

    monkeypatch.setattr(api, "_get", fake_get)
    monkeypatch.setattr(api, "RAW_DIR", tmp_path)

    prices = api.download_prices(date(2026, 1, 1), date(2026, 1, 20))
    assert sum("market-index" in u for u, _ in calls) == 3  # 7 + 7 + 6 days, from 31 Dec
    assert prices["start_time"].is_monotonic_increasing and prices["price"].eq(100).all()

    ndf = api.download_forecasts("NDF", "demand", date(2026, 1, 1), date(2026, 1, 5))
    assert len(ndf) == 5  # publishes on 31 Dec to 4 Jan
    assert (ndf["publish_time"].dt.hour == 7).all()

    n = len(calls)
    api.download_prices(date(2026, 1, 1), date(2026, 1, 20))
    assert len(calls) == n  # second run comes from the cache


def test_download_prices_keeps_whole_uk_days(monkeypatch, tmp_path):
    # In summer the UK day starts at 23:00 UTC the evening before. The download
    # must include that first hour and must not leave a stub of the day after.
    def fake_get(url, params, retries=4):
        t = pd.date_range(pd.Timestamp(params["from"]), pd.Timestamp(params["to"]), freq="30min")
        return {"data": [{"startTime": x.strftime("%Y-%m-%dT%H:%M:%SZ"), "price": 50.0,
                          "volume": 10.0} for x in t]}

    monkeypatch.setattr(api, "_get", fake_get)
    monkeypatch.setattr(api, "RAW_DIR", tmp_path)
    prices = api.download_prices(date(2026, 7, 1), date(2026, 7, 3))
    uk = prices["start_time"].dt.tz_convert("Europe/London")
    assert uk.dt.date.value_counts().to_dict() == {date(2026, 7, 1): 48, date(2026, 7, 2): 48}
    assert prices["start_time"].iloc[0] == pd.Timestamp("2026-06-30T23:00Z")

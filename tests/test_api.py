from datetime import datetime, timedelta, timezone

import math

from pipeline import api

# Shapes copied from real Elexon responses (values shortened)
MID = {"metadata": {"datasets": ["MID"]}, "data": [
    {"startTime": "2026-09-01T03:00:00Z", "dataProvider": "APXMIDP", "settlementDate": "2026-09-01",
     "settlementPeriod": 9, "price": 123.23, "volume": 1605.8},
    {"startTime": "2026-09-01T02:30:00Z", "dataProvider": "APXMIDP", "settlementDate": "2026-09-01",
     "settlementPeriod": 8, "price": 0, "volume": 0},
    {"startTime": "2026-09-01T02:00:00Z", "dataProvider": "APXMIDP", "settlementDate": "2026-09-01",
     "settlementPeriod": 7, "price": -6.44, "volume": 2367.45},
]}
NDF = {"data": [
    {"dataset": "NDF", "demand": 17605, "publishTime": "2026-08-31T11:48:00Z",
     "startTime": "2026-08-31T12:00:00Z", "settlementDate": "2026-08-31", "settlementPeriod": 27,
     "boundary": "N"}]}
WINDFOR = {"data": [
    {"dataset": "WINDFOR", "publishTime": "2026-08-31T10:30:00Z",
     "startTime": "2026-08-30T20:00:00Z", "generation": 6644}]}

NDFD = {"data": [
    {"dataset": "NDFD", "publishTime": "2024-01-13T14:45:00Z", "forecastDate": "2024-01-15",
     "demand": 43640}]}


def test_chunks_cover_range_without_gaps():
    s = datetime(2026, 1, 1, tzinfo=timezone.utc)
    e = datetime(2026, 1, 20, tzinfo=timezone.utc)
    parts = list(api.chunks(s, e, timedelta(days=7)))
    assert parts[0][0] == s and parts[-1][1] == e
    assert all(a[1] == b[0] for a, b in zip(parts, parts[1:]))
    assert all(b - a <= timedelta(days=7) for a, b in parts)


def test_parse_mid_sets_zero_volume_to_missing_and_keeps_negative_prices():
    df = api.parse_mid(MID)
    assert len(df) == 3
    assert math.isnan(df.loc[1, "price"])
    assert df.loc[2, "price"] == -6.44
    assert str(df["start_time"].dt.tz) == "UTC"


def test_parse_forecasts():
    d = api.parse_forecast(NDF, "demand")
    w = api.parse_forecast(WINDFOR, "generation")
    assert list(d.columns) == ["publish_time", "start_time", "value"]
    assert d.loc[0, "value"] == 17605 and w.loc[0, "value"] == 6644


def test_parse_empty():
    assert api.parse_mid({"data": []}).empty
    assert api.parse_forecast({"data": []}, "demand").empty


def test_parse_ndfd():
    df = api.parse_ndfd(NDFD)
    assert list(df.columns) == ["publish_time", "forecast_date", "value"]
    assert df.loc[0, "value"] == 43640 and str(df.loc[0, "forecast_date"]) == "2024-01-15"
    assert api.parse_ndfd({"data": []}).empty

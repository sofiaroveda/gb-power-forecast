from datetime import date

import pandas as pd

from pipeline import features


def test_cutoff_and_uk_delivery_date():
    # 23:30 UTC on 1 July is 00:30 UK time on 2 July (BST)
    prices = pd.DataFrame({"start_time": pd.to_datetime(["2026-07-01T23:30Z", "2026-01-15T12:00Z"]),
                           "price": [50.0, 60.0]})
    rows = features.delivery_frame(prices)
    summer = rows[rows["start_time"] == pd.Timestamp("2026-07-01T23:30Z")].iloc[0]
    assert summer["delivery_date"] == date(2026, 7, 2)
    assert summer["cutoff"] == pd.Timestamp("2026-07-01T08:00Z")
    winter = rows[rows["start_time"] == pd.Timestamp("2026-01-15T12:00Z")].iloc[0]
    assert winter["cutoff"] == pd.Timestamp("2026-01-14T08:00Z")


def test_uses_latest_forecast_published_before_cutoff(synthetic):
    prices, demand, wind, peak = synthetic
    df = features.build(prices, demand, wind, peak)
    early = demand[demand["publish_time"].dt.hour == 7].set_index("start_time")["value"]
    row = df.iloc[5000]
    assert row["demand_fc"] == early[row["start_time"]]


def test_hourly_wind_covers_both_half_hours(synthetic):
    prices, demand, wind, peak = synthetic
    df = features.build(prices, demand, wind, peak).set_index("start_time")
    t = df.index[5000].floor("h")
    assert df.loc[t, "wind_fc"] == df.loc[t + pd.Timedelta(minutes=30), "wind_fc"]
    assert df["wind_fc"].iloc[100:].notna().all()


def test_price_lags(synthetic):
    prices, demand, wind, peak = synthetic
    df = features.build(prices, demand, wind, peak).set_index("start_time")
    p = prices.set_index("start_time")["price"]
    t = df.index[3000]
    assert df.loc[t, "lag_2d"] == p[t - pd.Timedelta(days=2)]
    assert df.loc[t, "lag_7d"] == p[t - pd.Timedelta(days=7)]
    window = p[(p.index >= df.loc[t, "cutoff"] - pd.Timedelta(hours=24)) &
               (p.index <= df.loc[t, "cutoff"] - pd.Timedelta(minutes=30))]
    assert abs(df.loc[t, "mean_last_24h"] - window.mean()) < 1e-9


def test_winter_demand_forecast_published_after_cutoff_is_not_used():
    # Real winter pattern: the half-hourly NDF covering tomorrow is published
    # at about 08:45 UTC, after the 08:00 UTC cutoff. Earlier publishes only
    # reach the first hours of tomorrow, so the rest must stay missing, and the
    # daily peak forecast published on D-2 fills in.
    t = pd.date_range("2024-01-15T00:00Z", periods=48, freq="30min")
    prices = pd.DataFrame({"start_time": t, "price": 80.0})
    early = pd.DataFrame({"publish_time": pd.Timestamp("2024-01-14T07:46Z"),
                          "start_time": t[:8], "value": 30000.0})
    day_ahead = pd.DataFrame({"publish_time": pd.Timestamp("2024-01-14T08:45Z"),
                              "start_time": t[8:], "value": 40000.0})
    demand = pd.concat([early, day_ahead], ignore_index=True)
    wind = pd.DataFrame({"publish_time": pd.Timestamp("2024-01-14T07:30Z"),
                         "start_time": t[t.minute == 0], "value": 5000.0})
    peak = pd.DataFrame({"publish_time": pd.to_datetime(["2024-01-13T14:45Z", "2024-01-14T14:45Z"]),
                         "forecast_date": [date(2024, 1, 15)] * 2, "value": [45000.0, 99999.0]})
    df = features.build(prices, demand, wind, peak)
    assert (df["demand_fc"].iloc[:8] == 30000).all()
    assert df["demand_fc"].iloc[8:].isna().all()
    assert (df["demand_peak_fc"] == 45000).all()

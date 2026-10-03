"""The live forecast must be made by exactly the procedure the backtest scores,
from only what was public when it was made."""

from datetime import date

import pandas as pd

from pipeline import export, features, model


def test_target_day_switches_at_the_cutoff():
    assert export.target_day(pd.Timestamp("2026-10-03T07:59Z")) == date(2026, 10, 3)
    assert export.target_day(pd.Timestamp("2026-10-03T08:00Z")) == date(2026, 10, 4)
    # 23:30 UTC on 3 Oct is already 4 Oct in the UK, before that day's 08:00 cutoff
    assert export.target_day(pd.Timestamp("2026-10-03T23:30Z")) == date(2026, 10, 4)


def test_add_day_handles_clock_changes():
    empty = pd.DataFrame({"start_time": pd.to_datetime([], utc=True), "price": []})
    assert len(features.add_day(empty, date(2026, 3, 29))) == 46
    assert len(features.add_day(empty, date(2026, 10, 25))) == 50
    assert export.periods_in(date(2026, 10, 25)) == 50


def test_live_forecast_matches_backtest_using_only_data_public_at_the_time(synthetic):
    prices, demand, wind, peak = synthetic
    day = date(2025, 6, 10)
    now = export.cutoff_for(day) + pd.Timedelta(minutes=20)  # a run at 08:20 UTC

    # what a live run would have seen: published prices and forecasts only
    p_live = prices[features.price_public_at(prices["start_time"]) <= now]
    d_live, w_live = demand[demand["publish_time"] <= now], wind[wind["publish_time"] <= now]
    k_live = peak[peak["publish_time"] <= now]
    live = model.walk_forward(features.build(features.add_day(p_live, day), d_live, w_live, k_live))

    backtest = model.walk_forward(features.build(prices, demand, wind, peak))
    a = live.loc[live["delivery_date"] == day, "model"].reset_index(drop=True)
    b = backtest.loc[backtest["delivery_date"] == day, "model"].reset_index(drop=True)
    assert len(a) == 48 and a.notna().all()
    pd.testing.assert_series_equal(a, b)

from datetime import date

import pandas as pd

from pipeline import export, ledger


def _rows(day: date, value: float = 50.0) -> pd.DataFrame:
    n = export.periods_in(day)
    t = pd.date_range(ledger.day_start(day), periods=n, freq="30min")
    return pd.DataFrame({"start_time": t, "model": value, "naive_2d": 40.0,
                         "naive_7d": 45.0, "mean_7d": 42.0})


def test_forecast_saved_once_and_never_changed(tmp_path):
    day = date(2026, 10, 4)
    cutoff = export.cutoff_for(day)
    now = cutoff + pd.Timedelta(minutes=20)
    path = ledger.record(_rows(day, 50.0), day, cutoff, now, tmp_path)
    assert path is not None and path.name == "2026-10-04.csv"
    first = path.read_text()
    # a second run the same day, with a different forecast, changes nothing
    assert ledger.record(_rows(day, 99.0), day, cutoff, now + pd.Timedelta(hours=1), tmp_path) is None
    assert path.read_text() == first
    saved = ledger.load_all(tmp_path)
    assert len(saved) == 48 and (saved["model"] == 50.0).all()


def test_not_saved_before_cutoff_or_after_the_day_starts(tmp_path):
    day = date(2026, 10, 4)
    cutoff = export.cutoff_for(day)
    assert ledger.record(_rows(day), day, cutoff, cutoff - pd.Timedelta(minutes=1), tmp_path) is None
    # 4 Oct starts at 23:00 UTC on 3 Oct (British Summer Time)
    assert ledger.day_start(day) == pd.Timestamp("2026-10-03T23:00Z")
    assert ledger.record(_rows(day), day, cutoff, pd.Timestamp("2026-10-03T23:00Z"), tmp_path) is None
    assert not list(tmp_path.iterdir())


def test_record_scores_only_complete_days(tmp_path):
    day = date(2026, 10, 4)
    ledger.record(_rows(day, 50.0), day, export.cutoff_for(day),
                  export.cutoff_for(day) + pd.Timedelta(hours=1), tmp_path)
    rows = _rows(day)
    prices = pd.DataFrame({"start_time": rows["start_time"], "price": 60.0})
    half = export.record_json(prices.iloc[:24], tmp_path)
    assert half["days"][0]["complete"] is False and half["totals"] is None
    full = export.record_json(prices, tmp_path)
    assert full["totals"]["mae_model"] == 10.0 and full["totals"]["mae_naive_2d"] == 20.0

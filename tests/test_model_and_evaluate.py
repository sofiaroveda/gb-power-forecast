import pandas as pd

from pipeline import evaluate, features, model


def test_scores_on_toy_data():
    df = pd.DataFrame({"price": [10.0, 20.0], "naive_2d": [12.0, 18.0], "naive_7d": [10.0, 20.0],
                       "mean_7d": [14.0, 16.0], "model": [11.0, 19.0],
                       "delivery_date": ["2026-01-01", "2026-01-02"]})
    s = evaluate.scores(df)
    assert s.loc["naive_2d", "mae"] == 2.0
    assert s.loc["model", "skill_vs_naive_2d"] == 0.5
    assert s.loc["naive_7d", "rmse"] == 0.0


def test_model_beats_naive_on_data_with_real_signal(synthetic):
    df = model.walk_forward(features.build(*synthetic))
    s = evaluate.scores(df)
    assert s.loc["model", "mae"] < s.loc["naive_2d", "mae"]
    # the first 90 days are kept for training only
    assert df["model"].iloc[: 48 * 60].isna().all()


def test_unfinished_day_is_not_scored():
    # data up to 16:30 UTC on 3 Oct: 3 Oct (UK) is not over, 2 Oct is
    t = pd.date_range("2026-10-01T23:00Z", "2026-10-03T16:30Z", freq="30min")
    df = pd.DataFrame({"start_time": t, "price": 50.0, "naive_2d": 40.0, "naive_7d": 40.0,
                       "mean_7d": 40.0, "model": 45.0})
    df["delivery_date"] = df["start_time"].dt.tz_convert("Europe/London").dt.date
    rows = evaluate.common_rows(df)
    assert set(rows["delivery_date"].astype(str)) == {"2026-10-02"} and len(rows) == 48

"""The most important test: a forecast must not change if we scramble
everything that happened after its cutoff.

This checks the code never reads past its own cutoff. The cutoff time itself
(08:00 UTC on the day before delivery) is pinned by the tests in
test_features.py, so moving it later would also fail the suite."""

import numpy as np
import pandas as pd

from pipeline import evaluate, features, model


def test_scrambling_the_future_does_not_change_past_forecasts(synthetic):
    prices, demand, wind, peak = synthetic
    split = pd.Timestamp("2025-05-20T08:00Z")  # cutoff for delivery day 21 May

    rng = np.random.default_rng(99)
    p2 = prices.copy()
    # every price not yet published at the split: Elexon publishes prices in late
    # batches, so a price counts as published 6 hours after its half-hour ends
    after = p2["start_time"] + pd.Timedelta(hours=6, minutes=30) > split
    p2.loc[after, "price"] = rng.normal(500, 300, after.sum())
    d2, w2, k2 = demand.copy(), wind.copy(), peak.copy()
    for fc in (d2, w2, k2):
        late = fc["publish_time"] > split
        fc.loc[late, "value"] = rng.normal(0, 1e5, late.sum())

    a = model.walk_forward(features.build(prices, demand, wind, peak))
    b = model.walk_forward(features.build(p2, d2, w2, k2))
    known = a["cutoff"] <= split
    assert known.sum() > 3000 and a.loc[known, "model"].notna().sum() > 1000
    for col in evaluate.FORECASTERS + features.FEATURES:
        pd.testing.assert_series_equal(a.loc[known, col], b.loc[known, col], check_names=False)

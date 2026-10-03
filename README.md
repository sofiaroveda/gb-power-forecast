# GB power price forecast

Forecasts of the half-hourly GB electricity price for tomorrow, made each morning from the demand and wind forecasts published by then, and tested walk-forward against simple baselines.

It is an analysis project, not a trading tool.

Website: https://sofiaroveda.github.io/gb-power-forecast/ (tomorrow's forecast, the last 14 days, the live record and the backtest results).

## The question

On the morning of day D-1, before the day-ahead auction, what will the price be in each half-hour of day D? The forecast may only use what was public at 08:00 UTC on D-1: the latest National Demand Forecast, the latest wind generation forecast, and prices that had already happened.

## Results

Walk-forward backtest from 1 April 2024 to 2 October 2026: 915 delivery days and 43,848 half-hours (numbers as of 3 October 2026; the website shows them updated daily). Every forecaster is scored on the same half-hours. January to March 2024 is used only for training, and the model is refitted at the start of each month.

| Forecast | MAE (£/MWh) | RMSE (£/MWh) | Skill vs same period two days ago |
|---|---|---|---|
| Same half-hour two days ago | 26.23 | 44.37 | 0% |
| Same half-hour a week ago | 27.55 | 45.53 | -5% |
| Average of that half-hour over the last 7 known days | 22.64 | 35.80 | 14% |
| Model | 17.62 | 28.82 | 33% |

Skill is 1 minus the forecaster's MAE divided by the naive forecast's MAE: 0% means no better than copying the price from two days earlier.

The model beats the best baseline (the 7-day average) by 22% on MAE. It has the lowest error in all ten full quarters, and its skill against the two-day naive forecast ranges from 17% to 47% by quarter. The median error falls less than the mean, from £15.09 to £12.49, so much of the gain comes from avoiding large misses.

I checked where the gain comes from by refitting without some inputs (`python -m pipeline.ablation`). Without recent prices the skill falls to 8%, and without the demand and wind forecasts it falls to 14%. Recent prices plus the wind forecast alone reach 30%. This matches how the GB market works: wind decides how much gas generation is needed, and recent prices carry the gas price level, which the model has no other way to see. As a check for look-ahead, adding the previous day's actual prices (mostly not known at 08:00) as an input lowers the MAE to £16.99, so the model is not already getting that information from somewhere.

The weakest quarter is July to September 2026 (MAE £30.04), when the monthly average price rose from £106 to £130 and prices became much more volatile. All the forecasters did badly then, and a model without a gas price cannot see a move like that coming.

## How it works

The data comes from Elexon's Insights Solution API, which is free and needs no API key. The target is the half-hourly Market Index price (APX). The inputs are the National Demand Forecast (NDF) and the wind generation forecast (WINDFOR), which are both republished several times a day, and the daily peak demand forecast (NDFD).

For each delivery day, the code picks the latest forecast published at or before 08:00 UTC the day before.

One thing the data showed: the half-hourly NDF that covers tomorrow is published at about 08:45 UK time. In summer that is 07:45 UTC, before the cutoff, but in winter it is 08:45 UTC, after it. From November to March only about 21% of tomorrow's half-hours have an NDF value published by 08:00 UTC. Moving the cutoff would be look-ahead, so instead the model also uses Elexon's daily peak demand forecast (NDFD), published every afternoon for 2 to 14 days ahead, which is always available. Missing NDF values are left missing, and the trees handle them.

The model is refitted at the start of each month using only prices that had happened by that month's first cutoff. `tests/test_no_lookahead.py` scrambles every price after a date, and every forecast published after it, and fails if any earlier forecast changes.

Prices are only treated as known once they could have been published. Elexon publishes the APX price in batches: on 3 October 2026 the price for 17:00 to 17:30 UTC was still missing at 18:36. So a price counts as known 6 hours after its half-hour ends, and at the 08:00 cutoff the latest price used is the one for 01:30 to 02:00. The first version assumed a price was known as soon as its half-hour ended, which let a few prices that were not yet published into the "last 24 hours" average. Fixing it barely changed the score (MAE £17.57 before, £17.62 after), and allowing only 2 hours would have given £17.56. Each live run saves the newest price it could download, so the 6 hours can be checked against what really happens.

The simplest baseline uses the price two days earlier, because at 08:00 on D-1 most of D-1's prices have not happened yet. Using yesterday's price would be look-ahead.

The model is gradient-boosted trees (scikit-learn) on the demand forecast, daily peak demand forecast, wind forecast, residual demand (demand minus wind), wind share, UK time of day, day of week, month and recent prices. It uses absolute-error loss because prices spike and the score is MAE.

Half-hours with zero traded volume are reported with a price of 0, so they are treated as missing. Negative prices are kept, since they really happen on windy nights with low demand.

## The daily forecast and the live record

A GitHub Actions workflow (`.github/workflows/update.yml`) runs every morning at 08:40 UTC. It downloads the latest data, makes the forecast for the next UK day with `python -m pipeline.export`, and republishes the website. The live forecast is made by the same walk-forward code that produced the backtest: the next day's half-hours are added with no price, and the model predicts them from what was public at the cutoff. `tests/test_export.py` checks that a live run gives exactly the backtest's forecast for that day.

Each forecast is also saved to `forecasts/YYYY-MM-DD.csv`, once its cutoff has passed and before its day starts. Saved files are never rewritten, and `python -m pipeline.check` fails, which blocks the deploy, if a later commit changes or deletes one. Commit times can be set by anyone on their own computer, so the stronger evidence is GitHub's record of when the workflow pushed each file. The record starts with the forecast for 4 October 2026.

If any step fails, nothing is committed or published, the website keeps the last good forecast, and GitHub emails me.

## Run it yourself

Requires Python 3.10+.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                  # 22 tests, about a minute
python -m pipeline.data --start 2024-01-01   # download (cached in data/raw/)
python -m pipeline.backtest             # writes results/ and prints the table
python -m pipeline.export               # tomorrow's forecast and the website data
python -m pipeline.ablation             # the inputs comparison (a few minutes)
python tools/serve.py                   # preview the website at http://localhost:8000
```

The first download makes about 2,200 small requests and took around 15 minutes from 2024. The default start is 2023-01-01.

Days are UK days (Europe/London), so clock-change days have 46 or 50 half-hours. Half-hours with no traded volume (23 since 2024) and one half-hour missing from the API (13 April 2024) are left out of the scoring.

```
pipeline/api.py       download and parse Elexon data
pipeline/data.py      save prices and forecasts to data/
pipeline/features.py  one row per half-hour, using only what was known at the cutoff
pipeline/model.py     baselines and the walk-forward model
pipeline/evaluate.py  MAE, RMSE and skill, overall and by month
pipeline/export.py    the live forecast and the JSON files for the website
pipeline/ledger.py    saves each live forecast once, before its day starts
pipeline/check.py     checks run before publishing (saved forecasts unchanged, sane values)
pipeline/ablation.py  the backtest re-run with groups of inputs left out
site/                 the website: plain HTML, CSS and JavaScript, no build step
forecasts/            every live forecast, one file per day
tests/                pytest, including the no-look-ahead test
```

## Limitations and next steps

- No gas price yet. Gas plants usually set the GB price, so a daily gas price would probably be the most useful input to add.
- Solar is not modelled separately; it partly shows up in the demand forecast.
- The forecast is a single number per half-hour, with no range.
- Next: a short written market note generated by an LLM, with a check that every number in the note matches the data.

## Data

Elexon Insights Solution API (https://data.elexon.co.uk). Not affiliated with Elexon.

## About me

Built by Sofia, a materials science and engineering student at Imperial College London, as a project in energy market forecasting.

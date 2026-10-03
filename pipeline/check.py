"""Checks run before anything is published.

    python -m pipeline.check --since <commit>        # record + site data
    python -m pipeline.check --ledger-only --since <commit>

1. Prediction record: every forecast file that existed at <commit> must still
   exist and be byte-for-byte the same. Forecasts can be added, never changed.
2. Site data: tomorrow's forecast has a value for every half-hour, all within
   a plausible range, and the backtest scored a sensible number of half-hours.

Exits with an error (so the GitHub Actions run fails) if anything is wrong.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRICE_RANGE = (-1000, 5000)  # £/MWh; GB prices have never left this range


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout


def ledger_problems(since: str) -> list[str]:
    problems = []
    old_files = _git("ls-tree", "-r", "--name-only", since, "--", "forecasts").split()
    for name in old_files:
        if not name.endswith(".csv"):
            continue
        path = ROOT / name
        if not path.exists():
            problems.append(f"{name} was deleted")
        elif path.read_text() != _git("show", f"{since}:{name}"):
            problems.append(f"{name} was changed")
    return problems


def site_problems(site_data: Path = ROOT / "site" / "data") -> list[str]:
    problems = []
    fc = json.loads((site_data / "forecast.json").read_text())
    values = fc["model"]
    if len(values) not in (46, 48, 50):
        problems.append(f"forecast has {len(values)} half-hours")
    bad = [v for v in values if v is None or not math.isfinite(v)
           or not PRICE_RANGE[0] <= v <= PRICE_RANGE[1]]
    if bad:
        problems.append(f"forecast has {len(bad)} missing or implausible values")
    bt = json.loads((site_data / "backtest.json").read_text())
    if bt["half_hours"] < 10_000:
        problems.append(f"backtest scored only {bt['half_hours']} half-hours")
    return problems


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--since", required=True, help="commit to compare the record with")
    p.add_argument("--ledger-only", action="store_true")
    args = p.parse_args(argv)
    problems = ledger_problems(args.since)
    if not args.ledger_only:
        problems += site_problems()
    for msg in problems:
        print(f"FAIL: {msg}")
    if problems:
        sys.exit(1)
    print("All checks passed")


if __name__ == "__main__":
    main()

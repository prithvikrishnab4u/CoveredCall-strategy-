"""Replay on META's real daily closes (Oct 2016 - Oct 2026).

Prices, gaps and earnings dates are real. Option prices are still modelled:
there is no free history of option chains, so each day's implied vol is taken
from the stock's own trailing 30-day realized vol (earnings days excluded,
since the chain model adds the earnings move separately), times an assumed
implied/realized ratio. That ratio is the one number we cannot observe here,
so every run is repeated at 1.0x, 1.15x and 1.3x.
"""

from __future__ import annotations

import csv
import math
from datetime import date
from pathlib import Path

from ..market_calendar import next_trading_day
from ..replay.scenarios import Scenario

# META reports after the close on these dates (checked against the volume/gap in the data).
EARNINGS = [date.fromisoformat(d) for d in (
    "2016-11-02",
    "2017-02-01", "2017-05-03", "2017-07-26", "2017-11-01",
    "2018-01-31", "2018-04-25", "2018-07-25", "2018-10-30",
    "2019-01-30", "2019-04-24", "2019-07-24", "2019-10-30",
    "2020-01-29", "2020-04-29", "2020-07-30", "2020-10-29",
    "2021-01-27", "2021-04-28", "2021-07-28", "2021-10-25",
    "2022-02-02", "2022-04-27", "2022-07-27", "2022-10-26",
    "2023-02-01", "2023-04-26", "2023-07-26", "2023-10-25",
    "2024-02-01", "2024-04-24", "2024-07-31", "2024-10-30",
    "2025-01-29", "2025-04-30", "2025-07-30", "2025-10-29",
    "2026-01-28", "2026-04-29", "2026-07-29",
    "2026-10-28",  # next print: estimate, not yet confirmed
)]

# META's dividend started in 2024 ($0.50, then $0.525 from 2025). Ex-dates from memory;
# the 2026 ones are approximate. They only matter for the ex-div guard.
EX_DIVS = [date.fromisoformat(d) for d in (
    "2024-02-21", "2024-06-14", "2024-09-16", "2024-12-16",
    "2025-03-14", "2025-06-16", "2025-09-22", "2025-12-15",
    "2026-03-16", "2026-06-15", "2026-09-15",
)]
DIVIDEND = 0.525


def load_closes(path: str | Path) -> dict[date, float]:
    with open(path, newline="") as f:
        return {date.fromisoformat(r["date"]): float(r["close"]) for r in csv.DictReader(f)}


def realized_vol_path(closes: dict[date, float], window: int = 30, floor: float = 0.20,
                      cap: float = 1.0) -> dict[date, float]:
    """Trailing annualized vol of daily log returns, skipping the day after each print."""
    days = sorted(closes)
    gap_days = {next_trading_day(e) for e in EARNINGS}
    rets: list[float] = []
    out: dict[date, float] = {}
    for prev, d in zip(days, days[1:]):
        if d not in gap_days:
            rets.append(math.log(closes[d] / closes[prev]))
        tail = rets[-window:]
        if len(tail) >= 10:
            mean = sum(tail) / len(tail)
            var = sum((r - mean) ** 2 for r in tail) / (len(tail) - 1)
            out[d] = min(cap, max(floor, math.sqrt(var * 252)))
        else:
            out[d] = 0.35
    out[days[0]] = out.get(days[1], 0.35)
    return out


def real_scenario(path: str | Path, iv_ratio: float) -> Scenario:
    closes = load_closes(path)
    rv = realized_vol_path(closes)
    return Scenario(
        name=f"META real closes, IV = {iv_ratio:.2f}x realized",
        description="Real prices and earnings dates; option prices modelled.",
        closes=dict(sorted(closes.items())),
        earnings_dates=EARNINGS, ex_div_dates=EX_DIVS, dividend=DIVIDEND,
        iv_path={d: v * iv_ratio for d, v in rv.items()},
    )

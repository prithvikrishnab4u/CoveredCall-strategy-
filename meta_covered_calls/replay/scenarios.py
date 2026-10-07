"""Price paths for the replay.

Each scenario is a seeded random walk plus scripted shocks aimed at a specific
rule: rallies into the strike, earnings gaps, news gaps, a rally into ex-div.
The calendar is synthetic: earnings and ex-div dates are plausible placeholders
in META's usual pattern, not real announced dates.
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from ..market_calendar import next_trading_day, trading_days_range

# Placeholder calendar in META's usual rhythm (earnings after the close on a Wednesday).
EARNINGS_2026 = [date(2026, 1, 28), date(2026, 4, 29), date(2026, 7, 29), date(2026, 10, 28), date(2027, 1, 27)]
EX_DIV_2026 = [date(2026, 3, 16), date(2026, 6, 15), date(2026, 9, 15), date(2026, 12, 15)]
DIVIDEND = 0.53


@dataclass
class Scenario:
    name: str
    description: str
    closes: dict[date, float]
    earnings_dates: list[date] = field(default_factory=lambda: list(EARNINGS_2026))
    ex_div_dates: list[date] = field(default_factory=lambda: list(EX_DIV_2026))
    dividend: float = DIVIDEND
    base_iv: float = 0.32


def _path(start: date, end: date, s0: float, mu: float, vol: float, seed: int,
          shocks: dict[date, float] | None = None, drift_overrides: dict[tuple[date, date], float] | None = None,
          ) -> dict[date, float]:
    """Daily closes. `shocks` adds a one-day return; `drift_overrides` changes annual drift over a range."""
    rng = random.Random(seed)
    days = trading_days_range(start, end)
    shocks = shocks or {}
    drift_overrides = drift_overrides or {}
    dt = 1 / 252
    out = {days[0]: s0}
    s = s0
    for d in days[1:]:
        m = mu
        for (a, b), override in drift_overrides.items():
            if a <= d <= b:
                m = override
        ret = (m - 0.5 * vol * vol) * dt + vol * math.sqrt(dt) * rng.gauss(0, 1)
        s *= math.exp(ret) * (1 + shocks.get(d, 0.0))
        out[d] = round(s, 2)
    return out


START, END, S0 = date(2026, 1, 2), date(2026, 12, 31), 650.0


def _after(d: date) -> date:
    return next_trading_day(d)


def builtin_scenarios() -> list[Scenario]:
    gap_up = {_after(e): 0.12 for e in EARNINGS_2026}
    gap_down = {_after(e): -0.11 for e in EARNINGS_2026}
    rally_bursts: dict[tuple[date, date], float] = {
        (date(2026, 2, 17), date(2026, 3, 3)): 1.6,
        (date(2026, 5, 26), date(2026, 6, 9)): 1.6,
        (date(2026, 8, 24), date(2026, 9, 8)): 1.6,
        (date(2026, 11, 16), date(2026, 12, 1)): 1.6,
    }
    return [
        Scenario("steady_grind", "Calm uptrend, ~15%/yr, 28% vol.",
                 _path(START, END, S0, 0.15, 0.28, seed=1)),
        Scenario("chop", "Flat, low-vol range.",
                 _path(START, END, S0, 0.0, 0.20, seed=2)),
        Scenario("rally_into_strikes", "Two-week rallies (~+6%) in the middle of each cycle.",
                 _path(START, END, S0, 0.10, 0.28, seed=3, drift_overrides=rally_bursts)),
        Scenario("earnings_gap_up", "+12% gap the morning after every earnings print.",
                 _path(START, END, S0, 0.05, 0.28, seed=4, shocks=gap_up)),
        Scenario("earnings_gap_down", "-11% gap after every print.",
                 _path(START, END, S0, 0.10, 0.28, seed=5, shocks=gap_down)),
        Scenario("news_gap_up", "Random +8-10% news gaps mid-cycle (not earnings).",
                 _path(START, END, S0, 0.08, 0.30, seed=6,
                       shocks={date(2026, 3, 4): 0.09, date(2026, 6, 4): 0.10, date(2026, 9, 3): 0.08,
                               date(2026, 12, 2): 0.09})),
        Scenario("rally_into_ex_div", "Sharp rally in the week before each ex-dividend date.",
                 _path(START, END, S0, 0.10, 0.28, seed=7,
                       drift_overrides={(e - timedelta(days=7), e): 3.0 for e in EX_DIV_2026})),
        Scenario("selloff_then_recovery", "-35%/yr drift in H1, +60%/yr in H2.",
                 _path(START, END, S0, 0.0, 0.35, seed=8,
                       drift_overrides={(START, date(2026, 6, 30)): -0.35, (date(2026, 7, 1), END): 0.60})),
        Scenario("melt_up", "Extreme: +80%/yr, 35% vol. Stress test for the defensive rolls.",
                 _path(START, END, S0, 0.80, 0.35, seed=9)),
    ]


def load_csv_scenario(path: str | Path, earnings: list[date], ex_divs: list[date],
                      dividend: float = DIVIDEND, base_iv: float = 0.32) -> Scenario:
    """Replay real closes from a CSV with columns: date,close (date as YYYY-MM-DD)."""
    closes: dict[date, float] = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            closes[date.fromisoformat(row["date"].strip()[:10])] = float(row["close"])
    return Scenario(Path(path).stem, f"Closes from {path}", dict(sorted(closes.items())),
                    earnings_dates=earnings, ex_div_dates=ex_divs, dividend=dividend, base_iv=base_iv)

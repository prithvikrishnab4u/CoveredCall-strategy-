"""Market regimes, Monte Carlo paths, and a stylized long history for research runs.

All paths are synthetic. "Anchored" paths hit exact returns between anchor
dates (e.g. +40% from January to June) while keeping realistic daily noise:
random daily returns are generated, then each segment gets a constant drift
correction so it lands exactly on its target.
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

from ..market_calendar import next_trading_day, trading_days_range
from ..replay.scenarios import DIVIDEND, EARNINGS_2026, EX_DIV_2026, Scenario


def anchored_path(anchors: list[tuple[date, float]], s0: float, vol: float, seed: int,
                  shocks: dict[date, float] | None = None) -> dict[date, float]:
    """Closes from anchors[0] to anchors[-1]. Each anchor is (date, cumulative multiple vs s0).

    Shocks (one-day returns, e.g. an earnings gap) are part of the segment's target, so a +12%
    gap inside a +40% segment still ends the segment at +40%.
    """
    rng = random.Random(seed)
    shocks = shocks or {}
    days = trading_days_range(anchors[0][0], anchors[-1][0])
    dt = 1 / 252
    log_ret = {d: vol * math.sqrt(dt) * rng.gauss(0, 1) + math.log1p(shocks.get(d, 0.0)) for d in days[1:]}

    for (a, ma), (b, mb) in zip(anchors, anchors[1:]):
        seg = [d for d in days[1:] if a < d <= b]
        noisy = [d for d in seg if d not in shocks]
        if not noisy:
            continue
        gap = math.log(mb / ma) - sum(log_ret[d] for d in seg)
        for d in noisy:
            log_ret[d] += gap / len(noisy)

    out = {days[0]: s0}
    s = s0
    for d in days[1:]:
        s *= math.exp(log_ret[d])
        out[d] = round(s, 2)
    return out


def drawdown_iv(closes: dict[date, float], base: float, slope: float, cap: float = 0.85) -> dict[date, float]:
    """Implied vol that rises as the stock falls from its running peak (what bear markets do)."""
    peak, out = 0.0, {}
    for d in sorted(closes):
        peak = max(peak, closes[d])
        out[d] = min(cap, base + slope * (1 - closes[d] / peak))
    return out


def quarterly_earnings(year: int) -> list[date]:
    """Last Wednesday of Jan/Apr/Jul/Oct: META's usual rhythm."""
    out = []
    for month in (1, 4, 7, 10):
        d = date(year, month + 1, 1) - timedelta(days=1)
        d -= timedelta(days=(d.weekday() - 2) % 7)
        out.append(d)
    return out


def quarterly_ex_divs(year: int) -> list[date]:
    out = []
    for month in (3, 6, 9, 12):
        d = date(year, month, 15)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        out.append(d)
    return out


# --------------------------------------------------------------------------- named regimes

Y0, Y1 = date(2026, 1, 2), date(2026, 12, 31)
S0 = 650.0


def bull_40() -> Scenario:
    closes = anchored_path([(Y0, 1.0), (date(2026, 6, 30), 1.40), (Y1, 1.45)], S0, vol=0.30, seed=11)
    return Scenario("bull_+40%_6mo", "+40% Jan-Jun, then drifts +5% into year-end.", closes, base_iv=0.32)


def bear_50() -> Scenario:
    closes = anchored_path([(Y0, 1.0), (date(2026, 9, 30), 0.50), (Y1, 0.53)], S0, vol=0.50, seed=12)
    return Scenario("bear_-50%", "-50% Jan-Sep, IV rising with the drawdown (35% -> ~65%).",
                    closes, iv_path=drawdown_iv(closes, base=0.35, slope=0.60))


def earnings_gap_12() -> Scenario:
    gaps = {next_trading_day(e): 0.12 for e in EARNINGS_2026}
    closes = anchored_path([(Y0, 1.0), (Y1, 1.35)], S0, vol=0.30, seed=13, shocks=gaps)
    return Scenario("earnings_gap_+12%", "+12% overnight gap after every print.", closes)


def earnings_moved_up(seed: int = 14, vol: float = 0.30) -> Scenario:
    """Stress: every print lands 3 weeks earlier than estimated, and the real date is only announced
    10 days ahead. Contracts opened or rolled under the estimate then sit right in the 5-day window,
    so the earnings-close rule has to do the work."""
    actual = [e - timedelta(days=21) for e in EARNINGS_2026]
    revisions = [(est, act, act - timedelta(days=10)) for est, act in zip(EARNINGS_2026, actual)]
    gaps = {next_trading_day(e): 0.12 for e in actual}
    target = 1.35 if seed == 14 else 1.0 + random.Random(seed).gauss(0.10, 0.25)
    closes = anchored_path([(Y0, 1.0), (Y1, max(0.3, target))], S0, vol=vol, seed=seed, shocks=gaps)
    return Scenario("earnings_moved_up_+12%" if seed == 14 else f"moved_{seed}", "Stress: print 3 weeks earlier than estimated, date announced only 10 days ahead, +12% gap.",
                    closes, earnings_dates=actual, earnings_revisions=revisions)


def chop() -> Scenario:
    closes = anchored_path([(Y0, 1.0), (date(2026, 4, 1), 1.06), (date(2026, 8, 1), 0.95), (Y1, 1.0)],
                           S0, vol=0.25, seed=15)
    return Scenario("sideways_chop", "Range-bound, 25% realized vol.", closes)


def regime_scenarios() -> list[Scenario]:
    return [bull_40(), bear_50(), earnings_gap_12(), earnings_moved_up(), chop()]


# --------------------------------------------------------------------------- Monte Carlo

def random_path(seed: int, years: int = 1) -> Scenario:
    """One random year (or more): random drift and vol, random earnings gaps and news jumps.

    IV is set from the path's own vol times a random variance premium (1.0-1.2x), the main
    assumption that drives covered-call income in any model.
    """
    rng = random.Random(seed)
    start = date(2026, 1, 2)
    end = date(2026 + years - 1, 12, 31)
    days = trading_days_range(start, end)
    drift = rng.gauss(0.12, 0.30)
    vol = rng.uniform(0.25, 0.50)
    iv_ratio = rng.uniform(1.0, 1.2)
    earnings = [e for y in range(2026, 2026 + years + 1) for e in quarterly_earnings(y)]
    ex_divs = [x for y in range(2026, 2026 + years) for x in quarterly_ex_divs(y)]

    shocks: dict[date, float] = {}
    for e in earnings:
        nxt = next_trading_day(e)
        if nxt <= end:
            shocks[nxt] = max(-0.30, min(0.30, rng.gauss(0.0, 0.09)))
    for d in days:
        if d not in shocks and rng.random() < 2 / 252:   # ~2 news jumps a year
            shocks[d] = rng.gauss(0.0, 0.06)

    dt = 1 / 252
    s, closes = S0, {days[0]: S0}
    for d in days[1:]:
        s *= math.exp((drift - 0.5 * vol * vol) * dt + vol * math.sqrt(dt) * rng.gauss(0, 1))
        s *= 1 + shocks.get(d, 0.0)
        closes[d] = round(s, 2)
    return Scenario(f"mc_{seed}", f"drift {drift:+.0%}, vol {vol:.0%}", closes,
                    earnings_dates=earnings, ex_div_dates=ex_divs, base_iv=vol * iv_ratio)


# --------------------------------------------------------------------------- stylized history

# Approximate calendar-year returns with a META-like shape, 2013-2024 (from memory, rounded;
# NOT real data). Second number is a rough realized vol for that year.
STYLIZED_YEARS: list[tuple[int, float, float]] = [
    (2013, 1.05, 0.45), (2014, 0.43, 0.35), (2015, 0.34, 0.28), (2016, 0.10, 0.28),
    (2017, 0.53, 0.20), (2018, -0.26, 0.40), (2019, 0.57, 0.30), (2020, 0.33, 0.45),
    (2021, 0.23, 0.32), (2022, -0.64, 0.60), (2023, 1.94, 0.38), (2024, 0.66, 0.32),
]


def stylized_history(seed: int = 21) -> Scenario:
    closes: dict[date, float] = {}
    iv: dict[date, float] = {}
    s = S0
    earnings = [e for y, _, _ in STYLIZED_YEARS for e in quarterly_earnings(y)] + quarterly_earnings(2025)[:1]
    for i, (year, ret, vol) in enumerate(STYLIZED_YEARS):
        start = date(year, 1, 2)
        while start.weekday() >= 5 or start in (date(year, 1, 1),):
            start += timedelta(days=1)
        gaps = {next_trading_day(e): random.Random(seed * 100 + i * 4 + j).gauss(0.0, 0.09)
                for j, e in enumerate(quarterly_earnings(year)) if next_trading_day(e).year == year}
        year_path = anchored_path([(start, 1.0), (date(year, 12, 31), 1 + ret)], s, vol, seed + i, gaps)
        for d, px in year_path.items():
            closes[d] = px
            iv[d] = vol * 1.1
        s = closes[max(closes)]
    # META started paying a dividend in 2024.
    ex_divs = quarterly_ex_divs(2024)
    return Scenario("stylized_2013_2024", "META-shaped 12-year path (approximate annual returns, not real data).",
                    dict(sorted(closes.items())), earnings_dates=earnings, ex_div_dates=ex_divs,
                    dividend=DIVIDEND, iv_path=iv)


__all__ = ["regime_scenarios", "random_path", "stylized_history", "EX_DIV_2026"]

"""Price math: profit %, time value, and the limit-order reprice ladder."""

from __future__ import annotations

import math

from .models import OptionQuote

_EPS = 1e-9


def profit_pct(entry_credit: float, current_mid: float) -> float:
    """Share of the entry credit already captured. 0.5 = half the premium is ours."""
    if entry_credit <= 0:
        return 0.0
    return (entry_credit - current_mid) / entry_credit


def intrinsic_value(spot: float, strike: float) -> float:
    return max(0.0, spot - strike)


def time_value(quote: OptionQuote, spot: float) -> float:
    return max(0.0, quote.mid - intrinsic_value(spot, quote.strike))


def single_leg_tick(price: float) -> float:
    """META is in the penny program: $0.01 under $3, $0.05 at $3 and above."""
    return 0.01 if price < 3.0 else 0.05


def _floor(x: float, tick: float) -> float:
    return round(math.floor(x / tick + _EPS) * tick, 2)


def _ceil(x: float, tick: float) -> float:
    return round(math.ceil(x / tick - _EPS) * tick, 2)


def _round(x: float, tick: float) -> float:
    return round(math.floor(x / tick + 0.5 + _EPS) * tick, 2)


def _walk(start: float, cap: float, step: float, upward: bool) -> list[float]:
    """Prices from start toward cap in `step` increments, always ending exactly at cap."""
    prices: list[float] = []
    p = start
    if upward:
        while p < cap - _EPS:
            prices.append(round(p, 2))
            p += step
    else:
        while p > cap + _EPS:
            prices.append(round(p, 2))
            p -= step
    prices.append(round(cap, 2))
    return prices


def buy_ladder(quote: OptionQuote, step: float, cap_fraction: float) -> list[float]:
    """Buy prices: start at mid, step up toward the ask, stop at cap_fraction of the spread."""
    cap_raw = quote.bid + cap_fraction * quote.spread
    tick = single_leg_tick(cap_raw)
    cap = _floor(cap_raw, tick)                 # never pay more than the cap
    start = min(_round(quote.mid, single_leg_tick(quote.mid)), cap)
    return _walk(start, cap, step, upward=True)


def sell_ladder(quote: OptionQuote, step: float, cap_fraction: float) -> list[float]:
    """Sell prices: start at mid, step down toward the bid, stop at cap_fraction of the spread."""
    cap_raw = quote.ask - cap_fraction * quote.spread
    tick = single_leg_tick(cap_raw)
    cap = _ceil(cap_raw, tick)                  # never accept less than the cap
    start = max(_round(quote.mid, single_leg_tick(quote.mid)), cap)
    return _walk(start, cap, step, upward=False)


def roll_net_cap(old: OptionQuote, new: OptionQuote, cap_fraction: float) -> float:
    """Worst net credit the roll ladder will accept (combo orders trade in $0.01)."""
    sell_cap = new.ask - cap_fraction * new.spread
    buy_cap = old.bid + cap_fraction * old.spread
    return _ceil(sell_cap - buy_cap, 0.01)


def roll_ladder(old: OptionQuote, new: OptionQuote, step: float, cap_fraction: float) -> list[float]:
    """Net-credit prices for a two-leg roll: start at net mid, step down to the net cap."""
    cap = roll_net_cap(old, new, cap_fraction)
    start = max(_round(new.mid - old.mid, 0.01), cap)
    return _walk(start, cap, step, upward=False)

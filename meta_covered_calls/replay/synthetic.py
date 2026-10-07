"""Synthetic META option chains built with Black-Scholes.

Not a market data source. It exists so the engine can be replayed through
many price paths with realistic shapes: delta that falls with strike,
premium that decays with time, IV that is elevated for expiries spanning
earnings and crushes afterwards, and bid/ask spreads that widen with price.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from ..market_calendar import is_trading_day
from ..models import OptionChain, OptionQuote


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(spot: float, strike: float, t: float, vol: float, r: float) -> tuple[float, float]:
    """European call price and delta."""
    if t <= 0 or vol <= 0:
        return max(0.0, spot - strike), 1.0 if spot > strike else 0.0
    sq = vol * math.sqrt(t)
    d1 = (math.log(spot / strike) + (r + 0.5 * vol * vol) * t) / sq
    d2 = d1 - sq
    price = spot * norm_cdf(d1) - strike * math.exp(-r * t) * norm_cdf(d2)
    return price, norm_cdf(d1)


def weekly_expiries(asof: date, horizon_days: int) -> list[date]:
    """Friday expiries (Thursday when Friday is a holiday) from asof through the horizon."""
    out = []
    d = asof + timedelta(days=(4 - asof.weekday()) % 7)
    while (d - asof).days <= horizon_days:
        e = d
        while not is_trading_day(e):
            e -= timedelta(days=1)
        if e >= asof:
            out.append(e)
        d += timedelta(days=7)
    return out


@dataclass(frozen=True)
class ChainModel:
    base_iv: float = 0.32
    earnings_move: float = 0.08      # one-stdev earnings-day move priced into options
    otm_call_skew: float = 0.10      # IV falls a little as call strikes go further OTM
    rate: float = 0.04
    strike_step: float = 5.0
    strike_range: float = 0.35       # strikes up to +35% above spot
    strike_floor: float = 0.25       # and down to -25% below
    horizon_days: int = 70
    min_spread: float = 0.02
    spread_pct: float = 0.03

    def iv(self, spot: float, strike: float, t: float, earnings_events: int) -> float:
        smile = self.base_iv * (1.0 - self.otm_call_skew * math.log(strike / spot))
        smile = max(0.10, smile)
        total_var = smile * smile * t + earnings_events * self.earnings_move ** 2
        return math.sqrt(total_var / t)

    def spread(self, mid: float) -> float:
        return max(self.min_spread, self.spread_pct * mid + 0.01)

    def step_for(self, spot: float) -> float:
        """Strike spacing ~0.75% of spot: $5 around today's META price, scaled for other levels."""
        target = spot * 0.0075
        for step in (1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0):
            if step >= target:
                return step
        return 100.0

    def build(self, symbol: str, asof: date, spot: float, earnings_dates: list[date],
              extra_strikes: tuple[float, ...] = ()) -> OptionChain:
        """`extra_strikes` keeps held contracts quoted even if the strike grid changes."""
        quotes = []
        step = self.step_for(spot)
        lo = math.floor(spot * (1 - self.strike_floor) / step) * step
        hi = math.ceil(spot * (1 + self.strike_range) / step) * step
        grid = set()
        k = lo
        while k <= hi + 1e-9:
            grid.add(round(k, 2))
            k += step
        strikes = sorted(grid | set(extra_strikes))

        for expiry in weekly_expiries(asof, self.horizon_days):
            days = (expiry - asof).days
            t = max(days, 0.5) / 365.0
            # Earnings is after the close, so an event on `asof` is still ahead of us.
            events = sum(1 for e in earnings_dates if asof <= e < expiry)
            for strike in strikes:
                vol = self.iv(spot, strike, t, events)
                price, delta = bs_call(spot, strike, t, vol, self.rate)
                half = self.spread(price) / 2
                bid = max(0.0, round(price - half, 2))
                ask = round(max(price + half, bid + 0.01), 2)
                if ask < 0.03 and strike not in extra_strikes:
                    continue  # strikes too far out to be quoted
                quotes.append(OptionQuote(expiry, strike, bid, ask, round(delta, 4)))
        return OptionChain(symbol, asof, round(spot, 2), tuple(quotes))

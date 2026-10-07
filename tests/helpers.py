"""Builders for engine tests. Chains come from the synthetic model so prices are realistic."""

from __future__ import annotations

from datetime import date

from meta_covered_calls.config import StrategyConfig
from meta_covered_calls.models import MarketContext, OptionChain, PortfolioState, Position, TrancheState
from meta_covered_calls.replay.synthetic import ChainModel

EARNINGS = date(2026, 4, 29)
LAST_EARNINGS = date(2026, 1, 28)


def make_market(today: date, spot: float, earnings: date | None = EARNINGS,
                last_earnings: date | None = LAST_EARNINGS, ex_div: date | None = None,
                dividend: float = 0.53, iv: float = 0.32) -> MarketContext:
    chain = ChainModel(base_iv=iv).build("META", today, spot, [earnings] if earnings else [])
    return MarketContext(today=today, chain=chain, next_earnings_date=earnings,
                         last_earnings_date=last_earnings, next_ex_div_date=ex_div,
                         dividend_per_share=dividend)


def with_chain(market: MarketContext, chain: OptionChain) -> MarketContext:
    return MarketContext(market.today, chain, market.next_earnings_date, market.last_earnings_date,
                         market.next_ex_div_date, market.dividend_per_share)


def position_at_profit(market: MarketContext, tranche: str, expiry: date, strike: float,
                       profit: float) -> Position:
    """A held contract whose entry credit makes today's mid equal to the requested profit %."""
    q = market.chain.get(expiry, strike)
    assert q is not None, f"no quote for {strike} {expiry}"
    entry = q.mid / (1 - profit)
    return Position(tranche=tranche, expiry=expiry, strike=strike, contracts=3,
                    entry_credit=entry, opened_on=market.today, cumulative_credit=entry)


def state_with(*positions: Position, cfg: StrategyConfig | None = None) -> PortfolioState:
    cfg = cfg or StrategyConfig()
    state = PortfolioState(tranches={t.name: TrancheState(t.name) for t in cfg.tranches})
    for p in positions:
        state.tranches[p.tranche].position = p
    return state

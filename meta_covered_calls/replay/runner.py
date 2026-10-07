"""Day-by-day replay of the engine over a price path, with independent rule checks.

Once per trading day (at the close) the runner builds a synthetic chain,
asks the engine what to do, fills the tickets, then checks the outcomes the
rulebook exists to prevent: assignment at expiry, early assignment before
ex-div, a short call held through earnings, a call ITM in expiration week,
more than 6 short calls, or anything written on Tranche C.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from ..config import StrategyConfig
from ..market_calendar import next_trading_day
from ..models import Decision, Instruction, MarketContext, PortfolioState
from ..pricing import buy_ladder, sell_ladder, time_value
from ..state_store import Fill, apply_fill, new_state
from ..strategy_engine import StrategyEngine
from .scenarios import Scenario
from .synthetic import ChainModel


@dataclass
class Event:
    day: date
    tranche: str
    action: str
    reason: str
    cash: float          # dollars in (+) or out (-) for the whole ticket
    spot: float
    message: str


@dataclass
class ReplayResult:
    scenario: Scenario
    fill_mode: str
    events: list[Event] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    encumbered_days: Counter = field(default_factory=Counter)
    trading_days: int = 0
    open_liability: float = 0.0   # cost to buy back whatever is still open at the end

    @property
    def realized_premium(self) -> float:
        return sum(e.cash for e in self.events)

    @property
    def net_premium(self) -> float:
        return self.realized_premium - self.open_liability

    def counts(self) -> Counter:
        return Counter(f"{e.action}:{e.reason}" for e in self.events if e.action != "EXPIRED")


def _fill_prices(decision: Decision, market: MarketContext, fill_mode: str,
                 cfg: StrategyConfig) -> Fill:
    chain = market.chain
    buy = sell = None
    for leg in decision.ticket.legs:
        q = chain.get(leg.expiry, leg.strike)
        if fill_mode == "mid":
            price = q.mid
        elif leg.instruction is Instruction.BUY_TO_CLOSE:
            price = buy_ladder(q, cfg.ladder_step, cfg.ladder_cap_spread_fraction)[-1]
        else:
            price = sell_ladder(q, cfg.ladder_step, cfg.ladder_cap_spread_fraction)[-1]
        if leg.instruction is Instruction.BUY_TO_CLOSE:
            buy = price
        else:
            sell = price
    return Fill(buy_price=buy, sell_price=sell)


def run_replay(scenario: Scenario, cfg: StrategyConfig | None = None, fill_mode: str = "mid",
               chain_model: ChainModel | None = None) -> ReplayResult:
    cfg = cfg or StrategyConfig()
    model = chain_model or ChainModel(base_iv=scenario.base_iv)
    engine = StrategyEngine(cfg)
    state: PortfolioState = new_state(cfg)
    result = ReplayResult(scenario, fill_mode)
    earnings = sorted(scenario.earnings_dates)
    ex_divs = sorted(scenario.ex_div_dates)
    days = sorted(scenario.closes)

    for day in days:
        spot = scenario.closes[day]
        chain = model.build(cfg.symbol, day, spot, earnings)
        market = MarketContext(
            today=day,
            chain=chain,
            next_earnings_date=next((e for e in earnings if e >= day), None),
            last_earnings_date=next((e for e in reversed(earnings) if e < day), None),
            next_ex_div_date=next((x for x in ex_divs if x >= day), None),
            dividend_per_share=scenario.dividend,
        )
        result.trading_days += 1

        for d in engine.evaluate(state, market):
            if d.ticket is None:
                continue
            fill = _fill_prices(d, market, fill_mode, cfg)
            qty = d.ticket.legs[0].quantity
            cash = ((fill.sell_price or 0.0) - (fill.buy_price or 0.0)) * 100 * qty
            result.events.append(Event(day, d.tranche, d.action.value, d.reason.value, round(cash, 2),
                                       spot, d.message))
            apply_fill(state, d, fill, day)

        _end_of_day_checks(state, market, scenario, cfg, result)

    # Whatever is still open at the end is a liability at its mid.
    last = days[-1]
    chain = model.build(cfg.symbol, last, scenario.closes[last], earnings)
    for t in state.tranches.values():
        if t.position:
            q = chain.get(t.position.expiry, t.position.strike)
            result.open_liability += q.mid * 100 * t.position.contracts
    return result


def _end_of_day_checks(state: PortfolioState, market: MarketContext, scenario: Scenario,
                       cfg: StrategyConfig, result: ReplayResult) -> None:
    day, spot = market.today, market.spot
    nxt = next_trading_day(day)
    shorts = state.total_short_contracts()
    if shorts > cfg.max_total_short_contracts:
        result.violations.append(f"{day}: {shorts} short calls open (cap {cfg.max_total_short_contracts})")

    for t in state.tranches.values():
        pos = t.position
        if pos is None:
            continue
        result.encumbered_days[t.name] += 1
        if not cfg.tranche(t.name).writable:
            result.violations.append(f"{day}: tranche {t.name} has a short call")
        if day in scenario.earnings_dates and pos.expiry > day:
            result.violations.append(f"{day}: {t.name} {pos.strike:g}C held through earnings")
        if pos.dte(day) <= 7 and spot > pos.strike:
            result.violations.append(f"{day}: {t.name} {pos.strike:g}C ITM in expiration week (spot {spot:.2f})")
        if nxt in scenario.ex_div_dates and pos.expiry >= nxt and spot > pos.strike:
            q = market.chain.get(pos.expiry, pos.strike)
            if q is not None and time_value(q, spot) < scenario.dividend:
                result.violations.append(f"{day}: {t.name} {pos.strike:g}C early-assignment risk before ex-div")
        if pos.expiry == day:
            if spot > pos.strike:
                result.violations.append(f"{day}: {t.name} {pos.strike:g}C ASSIGNED at expiry (spot {spot:.2f})")
            result.events.append(Event(day, t.name, "EXPIRED", "EXPIRED", 0.0, spot,
                                       f"{pos.strike:g}C expired worthless"))
            t.position = None

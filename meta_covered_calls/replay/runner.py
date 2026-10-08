"""Day-by-day replay of the engine over a price path, with independent rule checks.

Once per trading day (at the close) the runner builds a synthetic chain,
asks the engine what to do, fills the tickets, then checks the outcomes the
rulebook exists to prevent: assignment at expiry, early assignment before
ex-div, a short call held through earnings, a call ITM in expiration week,
more than 6 short calls, or anything written on Tranche C.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date

from ..config import StrategyConfig
from ..market_calendar import next_trading_day, trading_days_until
from ..models import Decision, Instruction, MarketContext, PortfolioState
from ..pricing import buy_ladder, sell_ladder, time_value
from ..state_store import Fill, apply_fill, new_state
from ..strategy_engine import StrategyEngine
from .scenarios import Scenario
from .synthetic import ChainModel

DEFENSIVE_REASONS = {"PROXIMITY", "EX_DIV_GUARD"}


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
class EarningsAudit:
    """What the book looked like around one earnings print."""

    earnings: date
    engine_saw: date | None      # the date the engine believed 10 trading days earlier
    max_shorts_in_window: int    # short calls open at any close within 5 trading days before the print
    closed_by_rule: int          # positions the earnings-window rule had to close
    gap_pct: float               # next-day move after the print


@dataclass
class ReplayResult:
    scenario: Scenario
    fill_mode: str
    events: list[Event] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    encumbered_days: Counter = field(default_factory=Counter)
    trading_days: int = 0
    open_liability: float = 0.0   # cost to buy back whatever is still open at the end
    max_shorts: int = 0
    covered_notional: float = 0.0  # sum over days of spot * writable shares, for yield math
    earnings_audit: list[EarningsAudit] = field(default_factory=list)

    @property
    def gross_premium(self) -> float:
        """Cash received from every call sold (opens and the sell leg of rolls)."""
        return sum(e.cash for e in self.events if e.action == "OPEN") + self._roll_sells

    _roll_sells: float = 0.0

    @property
    def realized_premium(self) -> float:
        return sum(e.cash for e in self.events)

    @property
    def net_premium(self) -> float:
        return self.realized_premium - self.open_liability

    @property
    def years(self) -> float:
        return self.trading_days / 252

    @property
    def net_yield(self) -> float:
        """Annualized net premium as a share of the average value of the 600 writable shares."""
        if not self.covered_notional:
            return 0.0
        return self.net_premium / (self.covered_notional / self.trading_days) / self.years

    @property
    def gross_yield(self) -> float:
        if not self.covered_notional:
            return 0.0
        return self.gross_premium / (self.covered_notional / self.trading_days) / self.years

    @property
    def defensive_rolls(self) -> int:
        return sum(1 for e in self.events if e.action == "ROLL" and e.reason in DEFENSIVE_REASONS)

    @property
    def defensive_closes(self) -> int:
        return sum(1 for e in self.events if e.action == "CLOSE" and e.reason in DEFENSIVE_REASONS)

    def counts(self) -> Counter:
        return Counter(f"{e.action}:{e.reason}" for e in self.events if e.action != "EXPIRED")

    def written_pct(self, tranche: str) -> float:
        return self.encumbered_days[tranche] / self.trading_days if self.trading_days else 0.0


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
    writable_shares = sum(t.contracts for t in cfg.tranches if t.writable) * 100
    shorts_by_day: dict[date, int] = {}
    rule_closes: Counter = Counter()

    for day in days:
        spot = scenario.closes[day]
        iv = scenario.iv_on(day)
        m = model if iv is None else replace(model, base_iv=iv)
        held = tuple(t.position.strike for t in state.tranches.values() if t.position)
        chain = m.build(cfg.symbol, day, spot, earnings, extra_strikes=held)
        seen = scenario.earnings_as_seen(day)
        market = MarketContext(
            today=day,
            chain=chain,
            next_earnings_date=next((e for e in seen if e >= day), None),
            last_earnings_date=next((e for e in reversed(earnings) if e < day), None),
            next_ex_div_date=next((x for x in ex_divs if x >= day), None),
            dividend_per_share=scenario.dividend,
        )
        result.trading_days += 1
        result.covered_notional += spot * writable_shares

        for d in engine.evaluate(state, market):
            if d.ticket is None:
                continue
            fill = _fill_prices(d, market, fill_mode, cfg)
            qty = d.ticket.legs[0].quantity
            cash = ((fill.sell_price or 0.0) - (fill.buy_price or 0.0)) * 100 * qty
            if d.action.value == "ROLL":
                result._roll_sells += fill.sell_price * 100 * qty
            if d.reason.value == "EARNINGS_WINDOW":
                actual = next((e for e in earnings if e >= day), None)
                rule_closes[actual] += 1
            result.events.append(Event(day, d.tranche, d.action.value, d.reason.value, round(cash, 2),
                                       spot, d.message))
            apply_fill(state, d, fill, day)

        _end_of_day_checks(state, market, scenario, cfg, result)
        shorts_by_day[day] = state.total_short_contracts()
        result.max_shorts = max(result.max_shorts, shorts_by_day[day])

    _audit_earnings(scenario, days, shorts_by_day, rule_closes, result)

    # Whatever is still open at the end is a liability at its mid.
    last = days[-1]
    held = tuple(t.position.strike for t in state.tranches.values() if t.position)
    chain = model.build(cfg.symbol, last, scenario.closes[last], earnings, extra_strikes=held)
    for t in state.tranches.values():
        if t.position:
            q = chain.get(t.position.expiry, t.position.strike)
            result.open_liability += q.mid * 100 * t.position.contracts
    return result


def _audit_earnings(scenario: Scenario, days: list[date], shorts_by_day: dict[date, int],
                    rule_closes: Counter, result: ReplayResult) -> None:
    for e in sorted(scenario.earnings_dates):
        if not (days[0] <= e <= days[-1]):
            continue
        near = [d for d in days if 0 <= (e - d).days <= 21]   # keep the trading-day counts cheap
        window = [d for d in near if trading_days_until(d, e) <= 5]
        lookback = [d for d in near if trading_days_until(d, e) == 10]
        seen = None
        if lookback:
            seen = next((x for x in scenario.earnings_as_seen(lookback[0]) if x >= lookback[0]), None)
        nxt = next((d for d in days if d > e), None)
        gap = scenario.closes[nxt] / scenario.closes[e] - 1 if nxt else 0.0
        result.earnings_audit.append(EarningsAudit(
            earnings=e, engine_saw=seen,
            max_shorts_in_window=max((shorts_by_day[d] for d in window), default=0),
            closed_by_rule=rule_closes[e], gap_pct=gap,
        ))


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

"""The rulebook, as code.

The engine is pure: it takes the portfolio state and a market snapshot and
returns one Decision per tranche. It never talks to a broker, never sleeps,
never mutates state. That is what makes it testable and replayable.

Order of evaluation for a tranche holding a short call:
  0. Earnings window (<= 5 trading days to earnings) -> close, no matter what.
  1. Ex-dividend guard                               -> roll out, else close.
  2. Proximity (spot >= 98% of strike)               -> roll up and out, else close.
  3. 50% profit                                      -> close.
  4. 21 DTE: >= 40% profit close, else roll          -> roll, else close.
  otherwise hold.

An idle tranche opens a new contract only if the earnings blackout allows it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from .config import StrategyConfig, TrancheConfig
from .market_calendar import trading_days_until
from .models import (
    Action,
    Decision,
    Instruction,
    MarketContext,
    OptionQuote,
    OrderLeg,
    OrderTicket,
    PortfolioState,
    Position,
    Reason,
)
from .pricing import (
    buy_ladder,
    profit_pct,
    roll_ladder,
    roll_net_cap,
    sell_ladder,
    time_value,
)
from .safety import validate_decisions


class RollGoal(str, Enum):
    DEFENSIVE = "DEFENSIVE"  # highest strike that still rolls for a credit
    RESET = "RESET"          # strike nearest the tranche's target delta


@dataclass(frozen=True)
class RollCandidate:
    quote: OptionQuote
    net_cap: float
    short_roll: bool  # True when it came from the 14 DTE fallback search


# ---------------------------------------------------------------------------
# Expiry rules (shared with the safety validator)
# ---------------------------------------------------------------------------

def open_expiry_allowed(expiry: date, earnings: date | None, cfg: StrategyConfig) -> bool:
    """New contracts: expiry at least N calendar days before earnings."""
    if earnings is None:
        return False
    return (earnings - expiry).days >= cfg.new_open_earnings_blackout_days


def short_roll_expiry_allowed(expiry: date, earnings: date | None, cfg: StrategyConfig) -> bool:
    """Fallback rolls: expiry at least N full trading days before earnings."""
    if earnings is None:
        return False
    return expiry < earnings and trading_days_until(expiry, earnings) >= cfg.short_roll_earnings_buffer_tdays


def ex_div_threshold(market: MarketContext, cfg: StrategyConfig) -> float:
    return market.dividend_per_share + cfg.ex_div_time_value_buffer


def ex_div_guard_active(expiry: date, market: MarketContext, cfg: StrategyConfig) -> bool:
    """True when a call expiring on `expiry` is exposed to the upcoming ex-dividend date."""
    ex = market.next_ex_div_date
    if ex is None or market.dividend_per_share <= 0:
        return False
    if not (market.today < ex <= expiry):
        return False
    return trading_days_until(market.today, ex) <= cfg.ex_div_guard_tdays


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class StrategyEngine:
    def __init__(self, config: StrategyConfig) -> None:
        self.cfg = config

    def evaluate(self, state: PortfolioState, market: MarketContext) -> list[Decision]:
        decisions: list[Decision] = []
        for tcfg in self.cfg.tranches:
            tstate = state.tranches.get(tcfg.name)
            position = tstate.position if tstate else None
            if position is not None:
                decisions.append(self._manage(position, tcfg, market))
            else:
                decisions.append(self._maybe_open(tcfg, market))
        earnings = market.next_earnings_date
        if earnings is None or earnings < market.today:
            decisions.append(Decision(
                tranche="ALL", action=Action.ALERT, reason=Reason.EARNINGS_UNKNOWN,
                message="Next earnings date unknown or stale: no new contracts or rolls until it is set.",
            ))
        validate_decisions(decisions, state, market, self.cfg)
        return decisions

    # -- managing an open position -------------------------------------------

    def _manage(self, pos: Position, tcfg: TrancheConfig, market: MarketContext) -> Decision:
        cfg = self.cfg
        quote = market.chain.get(pos.expiry, pos.strike)
        if quote is None:
            return Decision(pos.tranche, Action.ALERT, Reason.NO_VALID_STRIKE,
                            f"No quote for held {pos.strike:g}C {pos.expiry}; cannot evaluate.")

        spot = market.spot
        dte = pos.dte(market.today)
        pnl = profit_pct(pos.entry_credit, quote.mid)
        summary = f"{pos.strike:g}C {pos.expiry} | spot {spot:.2f} | DTE {dte} | profit {pnl:.0%}"

        # 0. Earnings window: close everything.
        earnings = market.next_earnings_date
        if earnings is not None and 0 <= trading_days_until(market.today, earnings) <= cfg.earnings_close_window_tdays:
            days = trading_days_until(market.today, earnings)
            return self._close(pos, quote, Reason.EARNINGS_WINDOW,
                               f"Earnings in {days} trading day(s): closing. {summary}")

        # 1. Ex-dividend guard.
        if ex_div_guard_active(pos.expiry, market, cfg):
            tv = time_value(quote, spot)
            threshold = ex_div_threshold(market, cfg)
            if tv < threshold:
                return self._roll_or_close(
                    pos, quote, tcfg, market, Reason.EX_DIV_GUARD, RollGoal.DEFENSIVE,
                    f"Ex-div {market.next_ex_div_date}: time value {tv:.2f} < {threshold:.2f}. {summary}",
                )

        # 2. Proximity defense.
        if spot >= pos.strike * cfg.proximity_pct:
            if not cfg.proximity_roll_enabled:
                return self._close(pos, quote, Reason.PROXIMITY,
                                   f"Spot within {1 - cfg.proximity_pct:.0%} of strike: closing. {summary}")
            return self._roll_or_close(
                pos, quote, tcfg, market, Reason.PROXIMITY, RollGoal.DEFENSIVE,
                f"Spot within {1 - cfg.proximity_pct:.0%} of strike. {summary}",
            )

        # 3. Profit target.
        if pnl >= cfg.profit_target_pct:
            return self._close(pos, quote, Reason.PROFIT_TARGET, f"Profit target hit. {summary}")

        # 4. Time stop.
        if dte <= cfg.time_stop_dte:
            if pnl >= cfg.time_stop_close_profit_pct:
                return self._close(pos, quote, Reason.TIME_STOP_PROFIT,
                                   f"{cfg.time_stop_dte} DTE with >= {cfg.time_stop_close_profit_pct:.0%} profit. {summary}")
            message = f"{cfg.time_stop_dte} DTE with < {cfg.time_stop_close_profit_pct:.0%} profit. {summary}"
            if cfg.time_stop_fallback == "hold" and self._find_roll(pos, quote, tcfg, market, RollGoal.RESET) is None:
                return Decision(pos.tranche, Action.HOLD, Reason.TIME_STOP_ROLL,
                                f"{message} No credit roll: holding; proximity rule still guards it.")
            return self._roll_or_close(pos, quote, tcfg, market, Reason.TIME_STOP_ROLL, RollGoal.RESET, message)

        return Decision(pos.tranche, Action.HOLD, Reason.NO_TRIGGER, f"Hold. {summary}")

    def _close(self, pos: Position, quote: OptionQuote, reason: Reason, message: str) -> Decision:
        cfg = self.cfg
        ladder = tuple(-p for p in buy_ladder(quote, cfg.ladder_step, cfg.ladder_cap_spread_fraction))
        ticket = OrderTicket(
            legs=(OrderLeg(Instruction.BUY_TO_CLOSE, cfg.symbol, pos.expiry, pos.strike, pos.contracts),),
            ladder=ladder,
            step_seconds=cfg.ladder_step_seconds,
        )
        return Decision(pos.tranche, Action.CLOSE, reason, message, ticket=ticket)

    def _roll_or_close(self, pos: Position, quote: OptionQuote, tcfg: TrancheConfig,
                       market: MarketContext, reason: Reason, goal: RollGoal, message: str) -> Decision:
        cand = self._find_roll(pos, quote, tcfg, market, goal)
        if cand is None:
            return self._close(pos, quote, reason, f"{message} No credit roll available: closing.")

        cfg = self.cfg
        new = cand.quote
        ticket = OrderTicket(
            legs=(
                OrderLeg(Instruction.BUY_TO_CLOSE, cfg.symbol, pos.expiry, pos.strike, pos.contracts),
                OrderLeg(Instruction.SELL_TO_OPEN, cfg.symbol, new.expiry, new.strike, pos.contracts),
            ),
            ladder=tuple(roll_ladder(quote, new, cfg.ladder_step, cfg.ladder_cap_spread_fraction)),
            step_seconds=cfg.ladder_step_seconds,
        )
        kind = "earnings-buffer roll" if cand.short_roll else "roll"
        new_dte = (new.expiry - market.today).days
        return Decision(
            pos.tranche, Action.ROLL, reason,
            f"{message} -> {kind} to {new.strike:g}C {new.expiry} ({new_dte} DTE, delta {new.delta:.2f}), "
            f"net credit {ticket.start_price:.2f} start / {ticket.cap_price:.2f} floor.",
            ticket=ticket, new_expiry=new.expiry, new_strike=new.strike,
        )

    def _find_roll(self, pos: Position, old: OptionQuote, tcfg: TrancheConfig,
                   market: MarketContext, goal: RollGoal) -> RollCandidate | None:
        cfg = self.cfg
        earnings = market.next_earnings_date
        if earnings is None:
            return None  # cannot prove the new contract clears earnings

        primary: list[date] = []
        fallback: list[date] = []
        for expiry in market.chain.expiries():
            if expiry <= pos.expiry:
                continue
            dte = (expiry - market.today).days
            if cfg.roll_dte_min <= dte <= cfg.roll_dte_max and open_expiry_allowed(expiry, earnings, cfg):
                primary.append(expiry)
            elif cfg.short_roll_min_dte <= dte <= cfg.roll_dte_max and short_roll_expiry_allowed(expiry, earnings, cfg):
                fallback.append(expiry)

        for expiries, is_short in ((primary, False), (fallback, True)):
            best = self._best_roll(pos, old, tcfg, market, goal, expiries, is_short)
            if best is not None:
                return best
        return None

    def _best_roll(self, pos: Position, old: OptionQuote, tcfg: TrancheConfig, market: MarketContext,
                   goal: RollGoal, expiries: list[date], is_short: bool) -> RollCandidate | None:
        cfg = self.cfg
        spot = market.spot
        cands: list[RollCandidate] = []
        for expiry in expiries:
            for q in market.chain.calls(expiry):
                # Up (never down), and clear of the proximity band so it doesn't re-trigger tomorrow.
                if q.strike < pos.strike or q.strike * cfg.proximity_pct <= spot or q.bid <= 0:
                    continue
                if goal is RollGoal.RESET and q.delta > tcfg.delta_max:
                    continue
                if goal is RollGoal.DEFENSIVE and q.delta > cfg.defensive_roll_max_delta:
                    continue
                if ex_div_guard_active(q.expiry, market, cfg) and time_value(q, spot) < ex_div_threshold(market, cfg):
                    continue
                net_cap = roll_net_cap(old, q, cfg.ladder_cap_spread_fraction)
                if net_cap < cfg.roll_min_net_credit:
                    continue
                cands.append(RollCandidate(q, net_cap, is_short))
        if not cands:
            return None
        if goal is RollGoal.DEFENSIVE:
            # Furthest strike from spot that still pays; prefer the shorter lock-up on ties.
            return max(cands, key=lambda c: (c.quote.strike, -c.quote.expiry.toordinal()))
        # RESET: closest to the tranche's target delta, then shorter expiry, then more credit.
        return min(cands, key=lambda c: (abs(c.quote.delta - tcfg.delta_target),
                                         c.quote.expiry.toordinal(), -c.net_cap))

    # -- opening a new position ----------------------------------------------

    def _maybe_open(self, tcfg: TrancheConfig, market: MarketContext) -> Decision:
        cfg = self.cfg
        if not tcfg.writable or tcfg.contracts == 0:
            return Decision(tcfg.name, Action.HOLD, Reason.NOT_WRITABLE, "Core shares: never written against.")

        earnings = market.next_earnings_date
        if earnings is None:
            return Decision(tcfg.name, Action.BLOCKED, Reason.EARNINGS_UNKNOWN,
                            "Idle: earnings date unknown, no new contracts.")

        last = market.last_earnings_date
        if last is not None and last <= market.today:
            sessions = trading_days_until(last, market.today)
            if sessions <= cfg.post_earnings_wait_sessions:
                return Decision(tcfg.name, Action.BLOCKED, Reason.POST_EARNINGS_WAIT,
                                f"Idle: {sessions} of {cfg.post_earnings_wait_sessions} post-earnings sessions done.")

        spot = market.spot
        band_mid = (tcfg.dte_min + tcfg.dte_max) / 2
        expiries = [
            e for e in market.chain.expiries()
            if tcfg.dte_min <= (e - market.today).days <= tcfg.dte_max and open_expiry_allowed(e, earnings, cfg)
        ]
        if not expiries:
            return Decision(tcfg.name, Action.BLOCKED, Reason.NO_VALID_EXPIRY,
                            f"Idle: no {tcfg.dte_min}-{tcfg.dte_max} DTE expiry clears the earnings "
                            f"blackout (earnings {earnings}).")

        best: OptionQuote | None = None
        best_key: tuple[float, float] | None = None
        for e in expiries:
            for q in market.chain.calls(e):
                if not (tcfg.delta_min <= q.delta <= tcfg.delta_max):
                    continue
                if q.strike <= spot or q.bid < cfg.min_open_bid:
                    continue
                if ex_div_guard_active(q.expiry, market, cfg) and time_value(q, spot) < ex_div_threshold(market, cfg):
                    continue
                key = (abs((e - market.today).days - band_mid), abs(q.delta - tcfg.delta_target))
                if best_key is None or key < best_key:
                    best, best_key = q, key
        if best is None:
            return Decision(tcfg.name, Action.BLOCKED, Reason.NO_VALID_STRIKE,
                            f"Idle: no strike in the {tcfg.delta_min}-{tcfg.delta_max} delta band.")

        ladder = tuple(sell_ladder(best, cfg.ladder_step, cfg.ladder_cap_spread_fraction))
        ticket = OrderTicket(
            legs=(OrderLeg(Instruction.SELL_TO_OPEN, cfg.symbol, best.expiry, best.strike, tcfg.contracts),),
            ladder=ladder,
            step_seconds=cfg.ladder_step_seconds,
        )
        dte = (best.expiry - market.today).days
        return Decision(
            tcfg.name, Action.OPEN, Reason.NEW_ENTRY,
            f"Sell {tcfg.contracts}x {best.strike:g}C {best.expiry} ({dte} DTE, delta {best.delta:.2f}), "
            f"credit {ladder[0]:.2f} start / {ladder[-1]:.2f} floor. Spot {spot:.2f}.",
            ticket=ticket, new_expiry=best.expiry, new_strike=best.strike,
        )

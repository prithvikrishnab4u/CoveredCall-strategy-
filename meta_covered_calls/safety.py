"""Last line of defence: independent checks on every decision the engine emits.

These re-check the rulebook from scratch rather than trusting the engine's own
logic. Any failure raises SafetyViolation and nothing gets sent anywhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .market_calendar import trading_days_until
from .models import Action, Decision, Instruction, MarketContext, PortfolioState

if TYPE_CHECKING:
    from .config import StrategyConfig


class SafetyViolation(RuntimeError):
    pass


def _fail(decision: Decision, why: str) -> None:
    raise SafetyViolation(f"[{decision.tranche} {decision.action.value}] {why}")


def validate_decisions(decisions: list[Decision], state: PortfolioState,
                       market: MarketContext, cfg: "StrategyConfig") -> None:
    projected = state.total_short_contracts()
    allowed = {Instruction.BUY_TO_CLOSE, Instruction.SELL_TO_OPEN}
    earnings = market.next_earnings_date

    for d in decisions:
        if d.ticket is None:
            if d.action in (Action.OPEN, Action.CLOSE, Action.ROLL):
                _fail(d, "order action without a ticket")
            continue

        tcfg = cfg.tranche(d.tranche)
        tstate = state.tranches.get(d.tranche)
        held = tstate.position if tstate else None

        for leg in d.ticket.legs:
            if leg.symbol != cfg.symbol:
                _fail(d, f"symbol {leg.symbol} != {cfg.symbol}")
            if leg.instruction not in allowed:
                _fail(d, f"instruction {leg.instruction} not allowed")
            if leg.quantity != 3 or leg.quantity != tcfg.contracts:
                _fail(d, f"quantity {leg.quantity} must be 3 (tranche size {tcfg.contracts})")

            if leg.instruction is Instruction.BUY_TO_CLOSE:
                if held is None or held.expiry != leg.expiry or abs(held.strike - leg.strike) > 1e-9:
                    _fail(d, "buy-to-close does not match the tranche's held contract")
                projected -= leg.quantity

            if leg.instruction is Instruction.SELL_TO_OPEN:
                if not tcfg.writable:
                    _fail(d, "sell-to-open on a non-writable tranche")
                if leg.strike <= market.spot:
                    _fail(d, f"sell-to-open strike {leg.strike:g} is not above spot {market.spot:.2f}")
                if earnings is None or leg.expiry >= earnings:
                    _fail(d, "new short call would be open through earnings (or earnings unknown)")
                if d.action is Action.OPEN:
                    if (earnings - leg.expiry).days < cfg.new_open_earnings_blackout_days:
                        _fail(d, "new contract expires inside the earnings blackout")
                    if held is not None:
                        _fail(d, "opening on a tranche that already holds a contract")
                elif d.action is Action.ROLL:
                    if leg.strike * cfg.proximity_pct <= market.spot:
                        _fail(d, "rolled strike sits inside the proximity band")
                    if trading_days_until(leg.expiry, earnings) < cfg.short_roll_earnings_buffer_tdays:
                        _fail(d, "rolled contract expires too close to earnings")
                else:
                    _fail(d, "sell-to-open only allowed for OPEN or ROLL")
                projected += leg.quantity

        if d.action is Action.ROLL:
            instr = [leg.instruction for leg in d.ticket.legs]
            if instr != [Instruction.BUY_TO_CLOSE, Instruction.SELL_TO_OPEN]:
                _fail(d, "a roll must be one ticket: buy-to-close then sell-to-open")
            if d.ticket.cap_price < cfg.roll_min_net_credit - 1e-9:
                _fail(d, f"roll floor {d.ticket.cap_price:.2f} is a net debit")
        if d.action is Action.CLOSE and [leg.instruction for leg in d.ticket.legs] != [Instruction.BUY_TO_CLOSE]:
            _fail(d, "a close must be a single buy-to-close")

    if projected > cfg.max_total_short_contracts:
        raise SafetyViolation(f"projected short calls {projected} > cap {cfg.max_total_short_contracts}")
    if projected * 100 > cfg.total_shares - cfg.core_shares:
        raise SafetyViolation("projected short calls would encumber the core shares")

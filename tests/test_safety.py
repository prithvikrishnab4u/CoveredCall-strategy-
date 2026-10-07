"""The safety validator must reject anything outside the rulebook, even if the engine emitted it."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from meta_covered_calls.config import StrategyConfig
from meta_covered_calls.models import Action, Decision, Instruction, OrderLeg, OrderTicket, Reason
from meta_covered_calls.safety import SafetyViolation, validate_decisions
from meta_covered_calls.strategy_engine import StrategyEngine

from .helpers import make_market, position_at_profit, state_with

CFG = StrategyConfig()
M = make_market(date(2026, 3, 2), 650.0)


def _open(tranche="A", qty=3, symbol="META", expiry=date(2026, 4, 2), strike=760.0) -> Decision:
    leg = OrderLeg(Instruction.SELL_TO_OPEN, symbol, expiry, strike, qty)
    return Decision(tranche, Action.OPEN, Reason.NEW_ENTRY, "", OrderTicket((leg,), (5.0,), 30))


def test_engine_output_passes():
    StrategyEngine(CFG).evaluate(state_with(), M)  # validates internally


def test_valid_open_passes():
    validate_decisions([_open()], state_with(), M, CFG)


@pytest.mark.parametrize("decision,why", [
    (_open(tranche="C"), "tranche C"),
    (_open(qty=4), "quantity"),
    (_open(symbol="AAPL"), "symbol"),
    (_open(strike=640.0), "strike below spot"),
    (_open(expiry=date(2026, 4, 17)), "inside 14-day blackout"),
    (_open(expiry=date(2026, 5, 15)), "spans earnings"),
])
def test_rejects_bad_open(decision, why):
    with pytest.raises(SafetyViolation):
        validate_decisions([decision], state_with(), M, CFG)


def test_rejects_seventh_contract():
    cfg = StrategyConfig()
    a = position_at_profit(M, "A", date(2026, 4, 2), 740.0, 0.2)
    b = replace(a, tranche="B")
    # Fake a third writable position by smuggling an open onto a tranche that already holds one.
    with pytest.raises(SafetyViolation):
        validate_decisions([_open(tranche="A")], state_with(a, b), M, cfg)


def test_rejects_open_that_would_exceed_cap():
    a = position_at_profit(M, "A", date(2026, 4, 2), 740.0, 0.2)
    b = replace(a, tranche="B")
    state = state_with(a, b)
    state.tranches["A"].position = None  # A idle; but pretend B's slot is doubled
    state.tranches["B"].position = replace(b, contracts=6)
    with pytest.raises(SafetyViolation):
        validate_decisions([_open(tranche="A")], state, M, CFG)


def test_rejects_close_of_contract_not_held():
    leg = OrderLeg(Instruction.BUY_TO_CLOSE, "META", date(2026, 4, 2), 700.0, 3)
    d = Decision("A", Action.CLOSE, Reason.PROFIT_TARGET, "", OrderTicket((leg,), (-1.0,), 30))
    with pytest.raises(SafetyViolation):
        validate_decisions([d], state_with(), M, CFG)


def test_rejects_debit_roll_and_roll_into_proximity_band():
    pos = position_at_profit(M, "A", date(2026, 3, 27), 660.0, -0.5)
    btc = OrderLeg(Instruction.BUY_TO_CLOSE, "META", pos.expiry, pos.strike, 3)
    good_sto = OrderLeg(Instruction.SELL_TO_OPEN, "META", date(2026, 4, 10), 690.0, 3)
    debit = Decision("A", Action.ROLL, Reason.PROXIMITY, "", OrderTicket((btc, good_sto), (0.10, -0.05), 30))
    with pytest.raises(SafetyViolation):
        validate_decisions([debit], state_with(pos), M, CFG)

    tight_sto = OrderLeg(Instruction.SELL_TO_OPEN, "META", date(2026, 4, 10), 660.0, 3)  # 660 * 0.98 = 646.8 < spot 650
    tight = Decision("A", Action.ROLL, Reason.PROXIMITY, "", OrderTicket((btc, tight_sto), (0.5,), 30))
    with pytest.raises(SafetyViolation):
        validate_decisions([tight], state_with(pos), M, CFG)


def test_config_refuses_writable_core_tranche():
    with pytest.raises(ValueError):
        StrategyConfig(tranches=[
            {"name": "A", "contracts": 3, "dte_min": 28, "dte_max": 35, "delta_min": 0.14, "delta_max": 0.16},
            {"name": "B", "contracts": 3, "dte_min": 40, "dte_max": 49, "delta_min": 0.10, "delta_max": 0.13},
            {"name": "C", "contracts": 3, "dte_min": 28, "dte_max": 35, "delta_min": 0.14, "delta_max": 0.16},
        ])

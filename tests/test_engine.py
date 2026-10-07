"""Every rule in the rulebook, one scenario at a time."""

from __future__ import annotations

from datetime import date

import pytest

from meta_covered_calls.config import StrategyConfig
from meta_covered_calls.market_calendar import trading_days_until
from meta_covered_calls.models import Action, Instruction, Reason
from meta_covered_calls.strategy_engine import StrategyEngine

from .helpers import EARNINGS, make_market, position_at_profit, state_with

CFG = StrategyConfig()
ENGINE = StrategyEngine(CFG)


def decide(state, market, tranche):
    return next(d for d in ENGINE.evaluate(state, market) if d.tranche == tranche)


# ---------------------------------------------------------------- earnings window

@pytest.mark.parametrize("profit", [0.60, 0.30, 0.10, 0.0, -0.80])
def test_earnings_window_closes_regardless_of_pnl(profit):
    m = make_market(date(2026, 4, 23), 650.0)  # 4 trading days to earnings
    pos = position_at_profit(m, "A", date(2026, 5, 1), 700.0, profit)
    d = decide(state_with(pos), m, "A")
    assert d.action is Action.CLOSE and d.reason is Reason.EARNINGS_WINDOW
    assert [leg.instruction for leg in d.ticket.legs] == [Instruction.BUY_TO_CLOSE]


def test_earnings_window_closes_tested_position_instead_of_rolling():
    m = make_market(date(2026, 4, 22), 690.0)  # exactly 5 trading days out
    assert trading_days_until(m.today, EARNINGS) == 5
    pos = position_at_profit(m, "B", date(2026, 5, 1), 700.0, -1.0)
    d = decide(state_with(pos), m, "B")
    assert d.action is Action.CLOSE and d.reason is Reason.EARNINGS_WINDOW


def test_six_trading_days_out_is_normal_management():
    m = make_market(date(2026, 4, 21), 650.0)
    assert trading_days_until(m.today, EARNINGS) == 6
    pos = position_at_profit(m, "A", date(2026, 5, 15), 760.0, 0.20)
    assert decide(state_with(pos), m, "A").reason is not Reason.EARNINGS_WINDOW


# ---------------------------------------------------------------- ex-dividend guard

def test_ex_div_guard_fires_when_time_value_below_dividend_plus_buffer():
    m = make_market(date(2026, 3, 11), 650.0, ex_div=date(2026, 3, 16))  # 3 trading days
    pos = position_at_profit(m, "A", date(2026, 3, 20), 720.0, 0.30)    # cheap call, little time value
    d = decide(state_with(pos), m, "A")
    assert d.reason is Reason.EX_DIV_GUARD
    assert d.action in (Action.ROLL, Action.CLOSE)


def test_ex_div_guard_beats_proximity_on_deep_itm_call():
    m = make_market(date(2026, 3, 11), 650.0, ex_div=date(2026, 3, 16))
    pos = position_at_profit(m, "A", date(2026, 3, 20), 540.0, -2.0)
    assert decide(state_with(pos), m, "A").reason is Reason.EX_DIV_GUARD


def test_ex_div_guard_quiet_four_trading_days_out():
    m = make_market(date(2026, 3, 10), 650.0, ex_div=date(2026, 3, 16))
    pos = position_at_profit(m, "A", date(2026, 3, 20), 720.0, 0.30)
    assert decide(state_with(pos), m, "A").reason is not Reason.EX_DIV_GUARD


def test_ex_div_guard_ignores_call_expiring_before_ex_div():
    m = make_market(date(2026, 3, 11), 650.0, ex_div=date(2026, 3, 16))
    pos = position_at_profit(m, "A", date(2026, 3, 13), 670.0, 0.30)
    assert decide(state_with(pos), m, "A").reason is not Reason.EX_DIV_GUARD


def test_ex_div_guard_quiet_when_time_value_is_rich():
    m = make_market(date(2026, 3, 11), 650.0, ex_div=date(2026, 3, 16))
    pos = position_at_profit(m, "B", date(2026, 4, 10), 720.0, 0.10)
    assert decide(state_with(pos), m, "B").reason is not Reason.EX_DIV_GUARD


# ---------------------------------------------------------------- proximity defense

def test_proximity_rolls_up_and_out_for_credit():
    m = make_market(date(2026, 3, 2), 650.0)
    pos = position_at_profit(m, "A", date(2026, 3, 27), 660.0, -0.5)  # 650 >= 660 * 0.98
    d = decide(state_with(pos), m, "A")
    assert d.action is Action.ROLL and d.reason is Reason.PROXIMITY
    assert d.new_strike >= pos.strike and d.new_strike * CFG.proximity_pct > m.spot
    assert 30 <= (d.new_expiry - m.today).days <= 45
    assert d.ticket.cap_price >= 0
    assert [leg.instruction for leg in d.ticket.legs] == [Instruction.BUY_TO_CLOSE, Instruction.SELL_TO_OPEN]


def test_proximity_closes_when_no_credit_roll_exists():
    m = make_market(date(2026, 3, 2), 700.0)
    pos = position_at_profit(m, "A", date(2026, 3, 27), 640.0, -3.0)  # deep ITM
    d = decide(state_with(pos), m, "A")
    assert d.action is Action.CLOSE and d.reason is Reason.PROXIMITY
    assert "No credit roll" in d.message


def test_proximity_beats_profit_target():
    m = make_market(date(2026, 3, 2), 650.0)
    pos = position_at_profit(m, "A", date(2026, 3, 27), 660.0, 0.60)
    assert decide(state_with(pos), m, "A").reason is Reason.PROXIMITY


def test_roll_falls_back_to_earnings_buffer_expiry():
    # 30-45 DTE expiries (Apr 24, May 1) all fail the 14-day blackout before Apr 29 earnings.
    m = make_market(date(2026, 3, 23), 650.0)
    pos = position_at_profit(m, "A", date(2026, 4, 2), 660.0, -0.5)
    d = decide(state_with(pos), m, "A")
    assert d.action is Action.ROLL
    assert (d.new_expiry - m.today).days >= CFG.short_roll_min_dte
    assert trading_days_until(d.new_expiry, EARNINGS) >= CFG.short_roll_earnings_buffer_tdays
    assert "earnings-buffer roll" in d.message


def test_rolls_never_span_earnings():
    for day in (date(2026, 3, 2), date(2026, 3, 16), date(2026, 3, 23), date(2026, 4, 6)):
        m = make_market(day, 650.0)
        exp = next(e for e in m.chain.expiries() if (e - day).days >= 7)
        pos = position_at_profit(m, "A", exp, 660.0, -0.5)
        d = decide(state_with(pos), m, "A")
        if d.action is Action.ROLL:
            assert d.new_expiry < EARNINGS
            assert trading_days_until(d.new_expiry, EARNINGS) >= 5


# ---------------------------------------------------------------- profit target and time stop

def test_profit_target_closes():
    m = make_market(date(2026, 3, 2), 650.0)
    pos = position_at_profit(m, "A", date(2026, 4, 2), 740.0, 0.55)
    d = decide(state_with(pos), m, "A")
    assert d.action is Action.CLOSE and d.reason is Reason.PROFIT_TARGET


def test_time_stop_closes_with_40pct_profit():
    m = make_market(date(2026, 3, 6), 650.0)
    pos = position_at_profit(m, "A", date(2026, 3, 27), 720.0, 0.45)  # 21 DTE
    d = decide(state_with(pos), m, "A")
    assert d.action is Action.CLOSE and d.reason is Reason.TIME_STOP_PROFIT


def test_time_stop_rolls_when_under_40pct():
    m = make_market(date(2026, 3, 6), 650.0)
    pos = position_at_profit(m, "A", date(2026, 3, 27), 720.0, 0.20)
    d = decide(state_with(pos), m, "A")
    assert d.action is Action.ROLL and d.reason is Reason.TIME_STOP_ROLL
    new = m.chain.get(d.new_expiry, d.new_strike)
    assert new.delta <= CFG.tranche("A").delta_max and d.new_strike >= 720.0


def test_time_stop_closes_when_no_expiry_clears_earnings():
    # 11 DTE on Apr 13: nothing >= 14 DTE expires 5+ trading days before Apr 29.
    m = make_market(date(2026, 4, 13), 650.0)
    pos = position_at_profit(m, "A", date(2026, 4, 24), 720.0, 0.10)
    d = decide(state_with(pos), m, "A")
    assert d.action is Action.CLOSE and d.reason is Reason.TIME_STOP_ROLL


def test_hold_when_nothing_triggers():
    m = make_market(date(2026, 3, 2), 650.0)
    pos = position_at_profit(m, "A", date(2026, 4, 2), 740.0, 0.20)
    assert decide(state_with(pos), m, "A").action is Action.HOLD


# ---------------------------------------------------------------- opening

def test_opens_tranche_a_in_band():
    m = make_market(date(2026, 3, 2), 650.0)
    d = decide(state_with(), m, "A")
    assert d.action is Action.OPEN
    q = m.chain.get(d.new_expiry, d.new_strike)
    assert 28 <= (d.new_expiry - m.today).days <= 35
    assert 0.14 <= q.delta <= 0.16
    assert d.ticket.legs[0].quantity == 3


def test_tranche_b_blocked_when_band_hits_blackout():
    m = make_market(date(2026, 3, 2), 650.0)  # 40-49 DTE = Apr 17, only 12 days before earnings
    d = decide(state_with(), m, "B")
    assert d.action is Action.BLOCKED and d.reason is Reason.NO_VALID_EXPIRY


def test_tranche_b_opens_after_earnings():
    m = make_market(date(2026, 2, 2), 650.0)
    d = decide(state_with(), m, "B")
    assert d.action is Action.OPEN
    assert 40 <= (d.new_expiry - m.today).days <= 49
    assert (EARNINGS - d.new_expiry).days >= 14


def test_tranche_c_never_opens():
    m = make_market(date(2026, 2, 2), 650.0)
    d = decide(state_with(), m, "C")
    assert d.action is Action.HOLD and d.ticket is None


@pytest.mark.parametrize("today,blocked", [
    (date(2026, 1, 29), True),   # 1 session after Jan 28 print
    (date(2026, 1, 30), True),   # 2 sessions
    (date(2026, 2, 2), False),   # 3rd session: allowed
])
def test_post_earnings_wait(today, blocked):
    m = make_market(today, 650.0)
    d = decide(state_with(), m, "A")
    assert (d.reason is Reason.POST_EARNINGS_WAIT) == blocked


def test_unknown_earnings_blocks_opens_and_alerts():
    m = make_market(date(2026, 3, 2), 650.0, earnings=None)
    decisions = ENGINE.evaluate(state_with(), m)
    assert all(d.action is not Action.OPEN for d in decisions)
    assert any(d.reason is Reason.EARNINGS_UNKNOWN and d.action is Action.ALERT for d in decisions)


def test_unknown_earnings_turns_rolls_into_closes():
    m = make_market(date(2026, 3, 2), 650.0, earnings=None)
    pos = position_at_profit(m, "A", date(2026, 3, 27), 660.0, -0.5)
    assert decide(state_with(pos), m, "A").action is Action.CLOSE

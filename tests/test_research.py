from __future__ import annotations

from datetime import date

from meta_covered_calls.config import StrategyConfig
from meta_covered_calls.models import Action, Reason
from meta_covered_calls.replay.runner import run_replay
from meta_covered_calls.research.regimes import anchored_path, bull_40, earnings_moved_up, quarterly_earnings
from meta_covered_calls.strategy_engine import StrategyEngine

from .helpers import make_market, position_at_profit, state_with


def test_anchored_path_hits_every_anchor():
    anchors = [(date(2026, 1, 2), 1.0), (date(2026, 6, 30), 1.40), (date(2026, 12, 31), 0.90)]
    closes = anchored_path(anchors, 100.0, vol=0.40, seed=3, shocks={date(2026, 3, 2): 0.12})
    assert abs(closes[date(2026, 6, 30)] - 140.0) < 0.05
    assert abs(closes[date(2026, 12, 31)] - 90.0) < 0.05


def test_quarterly_earnings_are_wednesdays():
    assert quarterly_earnings(2026) == [date(2026, 1, 28), date(2026, 4, 29), date(2026, 7, 29), date(2026, 10, 28)]


def test_engine_sees_estimate_until_announcement():
    s = earnings_moved_up()
    est, actual, announced = s.earnings_revisions[1]
    assert est in s.earnings_as_seen(date(2026, 3, 2)) and actual not in s.earnings_as_seen(date(2026, 3, 2))
    assert actual in s.earnings_as_seen(announced)


def test_regime_replay_flat_into_every_print():
    r = run_replay(bull_40(), fill_mode="cap")
    assert r.violations == [] and r.max_shorts <= 6
    assert all(a.max_shorts_in_window == 0 for a in r.earnings_audit)


# ---------------------------------------------------------------- policy knobs

def _decide(cfg, state, market, tranche):
    return next(d for d in StrategyEngine(cfg).evaluate(state, market) if d.tranche == tranche)


def test_proximity_close_only_policy():
    m = make_market(date(2026, 3, 2), 650.0)
    pos = position_at_profit(m, "A", date(2026, 3, 27), 660.0, -0.5)
    d = _decide(StrategyConfig(proximity_roll_enabled=False), state_with(pos), m, "A")
    assert d.action is Action.CLOSE and d.reason is Reason.PROXIMITY


def test_defensive_roll_delta_cap():
    m = make_market(date(2026, 3, 2), 650.0)
    pos = position_at_profit(m, "A", date(2026, 3, 27), 660.0, -0.5)
    d = _decide(StrategyConfig(defensive_roll_max_delta=0.30), state_with(pos), m, "A")
    if d.action is Action.ROLL:
        assert m.chain.get(d.new_expiry, d.new_strike).delta <= 0.30
    else:
        assert d.action is Action.CLOSE


def test_time_stop_hold_fallback():
    m = make_market(date(2026, 4, 13), 650.0)
    pos = position_at_profit(m, "A", date(2026, 4, 24), 720.0, 0.10)  # no roll clears earnings
    d = _decide(StrategyConfig(time_stop_fallback="hold"), state_with(pos), m, "A")
    assert d.action is Action.HOLD and d.reason is Reason.TIME_STOP_ROLL


# ---------------------------------------------------------------- real data

def test_real_closes_cover_every_trading_day():
    from meta_covered_calls.market_calendar import trading_days_range
    from meta_covered_calls.research.real import EARNINGS, load_closes, realized_vol_path

    closes = load_closes("data/meta_daily.csv")
    days = sorted(closes)
    assert set(days) == set(trading_days_range(days[0], days[-1]))
    assert all(0.2 <= v <= 1.0 for v in realized_vol_path(closes).values())
    # Every listed print except the unreported next one shows up as a real move in the data.
    from meta_covered_calls.market_calendar import next_trading_day
    moves = [abs(closes[next_trading_day(e)] / closes[e] - 1) for e in EARNINGS if next_trading_day(e) in closes]
    assert len(moves) == 40 and sum(m > 0.03 for m in moves) >= 30

from __future__ import annotations

from datetime import date

from meta_covered_calls.config import StrategyConfig
from meta_covered_calls.market_calendar import is_trading_day, nyse_holidays, trading_days_until
from meta_covered_calls.models import Action, Decision, Instruction, OptionQuote, OrderLeg, OrderTicket, Reason
from meta_covered_calls.pricing import buy_ladder, profit_pct, roll_ladder, roll_net_cap, sell_ladder, time_value
from meta_covered_calls.state_store import Fill, apply_fill, load_state, new_state, save_state

E = date(2026, 4, 17)


def q(bid, ask, strike=700.0, delta=0.15):
    return OptionQuote(E, strike, bid, ask, delta)


# ---------------------------------------------------------------- ladder

def test_buy_ladder_penny_tick():
    assert buy_ladder(q(2.00, 2.40), 0.05, 0.60) == [2.20, 2.24]


def test_buy_ladder_nickel_tick_above_3():
    assert buy_ladder(q(4.00, 5.00), 0.05, 0.60) == [4.50, 4.55, 4.60]


def test_sell_ladder_steps_down_to_cap():
    assert sell_ladder(q(4.00, 5.00), 0.05, 0.60) == [4.50, 4.45, 4.40]


def test_tight_spread_ladder_is_single_price():
    assert buy_ladder(q(1.00, 1.02), 0.05, 0.60) == [1.01]


def test_buy_cap_never_exceeds_60pct_of_spread():
    for bid, ask in [(0.50, 0.73), (3.10, 3.65), (10.0, 10.9), (1.23, 1.31)]:
        ladder = buy_ladder(q(bid, ask), 0.05, 0.60)
        assert ladder[-1] <= bid + 0.6 * (ask - bid) + 1e-9
        assert ladder == sorted(ladder)


def test_roll_ladder_ends_at_net_cap():
    old, new = q(5.00, 5.40, 700), q(6.00, 6.40, 720)
    ladder = roll_ladder(old, new, 0.05, 0.60)
    assert ladder[0] == 1.00
    assert ladder[-1] == roll_net_cap(old, new, 0.60) == 0.92
    assert ladder == sorted(ladder, reverse=True)


def test_profit_and_time_value():
    assert profit_pct(4.0, 2.0) == 0.5
    assert time_value(q(9.8, 10.2, strike=640), spot=650.0) == 0.0  # mid 10 == intrinsic 10
    assert abs(time_value(q(10.4, 10.8, strike=640), spot=650.0) - 0.6) < 1e-9


# ---------------------------------------------------------------- calendar

def test_2026_holidays():
    h = nyse_holidays(2026)
    for d in [date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25),
              date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25)]:
        assert d in h, d
    assert len(h) == 10


def test_saturday_new_year_not_observed_on_friday():
    assert is_trading_day(date(2021, 12, 31))


def test_trading_days_until():
    assert trading_days_until(date(2026, 4, 23), date(2026, 4, 29)) == 4
    assert trading_days_until(date(2026, 4, 2), date(2026, 4, 6)) == 1   # Good Friday skipped
    assert trading_days_until(date(2026, 4, 29), date(2026, 4, 29)) == 0


# ---------------------------------------------------------------- state

def _ticket(*legs):
    return OrderTicket(tuple(legs), (1.0,), 30)


def test_open_roll_close_lifecycle_and_persistence(tmp_path):
    cfg = StrategyConfig()
    state = new_state(cfg)
    sto = OrderLeg(Instruction.SELL_TO_OPEN, "META", date(2026, 4, 2), 740.0, 3)
    apply_fill(state, Decision("A", Action.OPEN, Reason.NEW_ENTRY, "", _ticket(sto)), Fill(sell_price=5.0),
               date(2026, 3, 2))
    assert state.tranches["A"].position.entry_credit == 5.0

    btc = OrderLeg(Instruction.BUY_TO_CLOSE, "META", date(2026, 4, 2), 740.0, 3)
    sto2 = OrderLeg(Instruction.SELL_TO_OPEN, "META", date(2026, 4, 10), 760.0, 3)
    apply_fill(state, Decision("A", Action.ROLL, Reason.PROXIMITY, "", _ticket(btc, sto2)),
               Fill(buy_price=8.0, sell_price=8.5), date(2026, 3, 9))
    pos = state.tranches["A"].position
    assert (pos.strike, pos.entry_credit, pos.roll_count) == (760.0, 8.5, 1)
    assert abs(pos.cumulative_credit - 5.5) < 1e-9

    path = tmp_path / "state.json"
    save_state(state, path)
    loaded = load_state(path, cfg)
    assert loaded.tranches["A"].position == pos
    assert loaded.tranches["C"].position is None

    btc2 = OrderLeg(Instruction.BUY_TO_CLOSE, "META", date(2026, 4, 10), 760.0, 3)
    apply_fill(loaded, Decision("A", Action.CLOSE, Reason.PROFIT_TARGET, "", _ticket(btc2)), Fill(buy_price=4.0),
               date(2026, 3, 20))
    assert loaded.tranches["A"].position is None


def test_option_symbol_format():
    leg = OrderLeg(Instruction.SELL_TO_OPEN, "META", date(2026, 11, 20), 702.5, 3)
    assert leg.option_symbol == "META  261120C00702500"

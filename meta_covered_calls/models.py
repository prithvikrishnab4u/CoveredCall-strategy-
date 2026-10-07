"""Plain data types shared by the engine, the replay, and (later) the broker layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


@dataclass(frozen=True)
class OptionQuote:
    """One call option. Prices are per share."""

    expiry: date
    strike: float
    bid: float
    ask: float
    delta: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True)
class OptionChain:
    symbol: str
    asof: date
    spot: float
    quotes: tuple[OptionQuote, ...]

    def expiries(self) -> list[date]:
        return sorted({q.expiry for q in self.quotes})

    def calls(self, expiry: date) -> list[OptionQuote]:
        return sorted((q for q in self.quotes if q.expiry == expiry), key=lambda q: q.strike)

    def get(self, expiry: date, strike: float) -> OptionQuote | None:
        for q in self.quotes:
            if q.expiry == expiry and abs(q.strike - strike) < 1e-9:
                return q
        return None


@dataclass(frozen=True)
class MarketContext:
    """Everything the engine needs to know about the outside world for one evaluation."""

    today: date
    chain: OptionChain
    # None means unknown: the engine then refuses to open anything new.
    next_earnings_date: date | None
    # Most recent earnings date already reported (drives the post-earnings wait).
    last_earnings_date: date | None = None
    next_ex_div_date: date | None = None
    dividend_per_share: float = 0.0

    @property
    def spot(self) -> float:
        return self.chain.spot


@dataclass
class Position:
    """A short call position held by one tranche."""

    tranche: str
    expiry: date
    strike: float
    contracts: int
    entry_credit: float          # per share, credit received when this contract was sold
    opened_on: date
    cumulative_credit: float = 0.0  # net credit across this tranche's whole roll chain
    roll_count: int = 0

    def dte(self, today: date) -> int:
        return (self.expiry - today).days


@dataclass
class TrancheState:
    name: str
    position: Position | None = None


@dataclass
class PortfolioState:
    tranches: dict[str, TrancheState] = field(default_factory=dict)

    def total_short_contracts(self) -> int:
        return sum(t.position.contracts for t in self.tranches.values() if t.position)


class Instruction(str, Enum):
    BUY_TO_CLOSE = "BUY_TO_CLOSE"
    SELL_TO_OPEN = "SELL_TO_OPEN"


class Action(str, Enum):
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    ROLL = "ROLL"
    HOLD = "HOLD"
    BLOCKED = "BLOCKED"   # idle tranche that may not open right now
    ALERT = "ALERT"       # something needs a human (e.g. earnings date unknown)


class Reason(str, Enum):
    EARNINGS_WINDOW = "EARNINGS_WINDOW"
    EX_DIV_GUARD = "EX_DIV_GUARD"
    PROXIMITY = "PROXIMITY"
    PROFIT_TARGET = "PROFIT_TARGET"
    TIME_STOP_PROFIT = "TIME_STOP_PROFIT"
    TIME_STOP_ROLL = "TIME_STOP_ROLL"
    NEW_ENTRY = "NEW_ENTRY"
    NO_TRIGGER = "NO_TRIGGER"
    NOT_WRITABLE = "NOT_WRITABLE"
    EARNINGS_UNKNOWN = "EARNINGS_UNKNOWN"
    POST_EARNINGS_WAIT = "POST_EARNINGS_WAIT"
    NO_VALID_EXPIRY = "NO_VALID_EXPIRY"
    NO_VALID_STRIKE = "NO_VALID_STRIKE"


@dataclass(frozen=True)
class OrderLeg:
    instruction: Instruction
    symbol: str
    expiry: date
    strike: float
    quantity: int

    @property
    def option_symbol(self) -> str:
        """Schwab/OCC format, e.g. 'META  261120C00700000'."""
        return f"{self.symbol:<6}{self.expiry:%y%m%d}C{round(self.strike * 1000):08d}"


@dataclass(frozen=True)
class OrderTicket:
    """One order to the broker. A roll is a single two-leg ticket.

    Prices are signed per-share net: positive = we receive a credit, negative = we pay.
    `ladder` is the full sequence of limit prices to try, in order, ending at the cap.
    """

    legs: tuple[OrderLeg, ...]
    ladder: tuple[float, ...]
    step_seconds: int

    @property
    def start_price(self) -> float:
        return self.ladder[0]

    @property
    def cap_price(self) -> float:
        return self.ladder[-1]


@dataclass(frozen=True)
class Decision:
    tranche: str
    action: Action
    reason: Reason
    message: str
    ticket: OrderTicket | None = None
    # For OPEN/ROLL: the contract that will be held afterwards.
    new_expiry: date | None = None
    new_strike: float | None = None

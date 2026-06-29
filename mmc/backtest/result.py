"""Backtest result types — the :class:`Trade` and :class:`BacktestResult`
dataclasses plus their derived statistics.

Everything is expressed in **R-multiples** so the simulator is
instrument-agnostic (transcript 11, ~16:18 — we think in 1:2 RR, not pips).
``risk = |entry - stop|`` is one ``R``; a winner that hit a 1:2 target is
``+2R``, a stopped-out trade is ``-1R``. Aggregates (win rate, expectancy,
profit factor, equity curve) all follow from the per-trade R values, so the same
numbers mean the same thing on EURUSD and XAUUSD.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import pandas as pd

from mmc.entry import Entry


class Outcome(Enum):
    """How a simulated trade resolved.

    ``WIN``      the take-profit was reached before the stop loss.
    ``LOSS``     the stop loss was reached (or hit first in an ambiguous bar).
    ``TIMEOUT``  ``max_hold`` bars elapsed with neither level hit — exit at the
                 last bar's close (transcript 11, ~24:32 — break even / manage
                 out when there's no reason to remain).
    ``NO_FILL``  price never traded into the entry zone, so no position opened.
    """

    WIN = "win"
    LOSS = "loss"
    TIMEOUT = "timeout"
    NO_FILL = "no_fill"


@dataclass
class Trade:
    """One simulated trade derived from an :class:`~mmc.entry.Entry`.

    ``entry``        the originating signal.
    ``outcome``      a :class:`Outcome`.
    ``fill_price``   the price the limit order filled at (``None`` if NO_FILL).
    ``fill_index``   integer bar position the fill happened on (``None`` if NO_FILL).
    ``exit_price``   the price the position closed at (``None`` if NO_FILL).
    ``exit_index``   integer bar position the exit happened on (``None`` if NO_FILL).
    ``r_multiple``   realised profit/loss in ``R`` units (risk = |entry - stop|).
                     ``+rr`` for a clean win, ``-1`` for a stop, the partial R at
                     close for a timeout, ``0`` for a no-fill.
    ``ambiguous``    True when SL and TP both sat inside the resolving bar's range
                     and we resolved conservatively (assumed the stop hit first).
    """

    entry: Entry
    outcome: Outcome
    fill_price: Optional[float] = None
    fill_index: Optional[int] = None
    exit_price: Optional[float] = None
    exit_index: Optional[int] = None
    r_multiple: float = 0.0
    ambiguous: bool = False

    @property
    def filled(self) -> bool:
        return self.outcome is not Outcome.NO_FILL

    @property
    def is_win(self) -> bool:
        return self.outcome is Outcome.WIN

    @property
    def is_loss(self) -> bool:
        return self.outcome is Outcome.LOSS

    @property
    def risk(self) -> float:
        """The trade's risk distance (one ``R``), taken from the entry signal."""
        return self.entry.risk

    @property
    def realized_rr(self) -> float:
        """Realised reward:risk ratio. Positive for wins, negative for losses,
        ``0`` for a flat exit / no-fill. Equal in magnitude to ``r_multiple``."""
        return self.r_multiple


@dataclass
class BacktestResult:
    """Aggregate statistics over a list of :class:`Trade` objects.

    All money-like quantities are in ``R`` units. ``equity_curve`` is the running
    cumulative ``R`` *over filled trades only* (a no-fill neither helps nor hurts
    the curve).
    """

    trades: List[Trade] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Trade counts
    # ------------------------------------------------------------------ #

    @property
    def filled_trades(self) -> List[Trade]:
        return [t for t in self.trades if t.filled]

    @property
    def num_trades(self) -> int:
        """Number of *filled* trades (no-fills are not trades)."""
        return len(self.filled_trades)

    @property
    def num_signals(self) -> int:
        """Total signals processed, including no-fills."""
        return len(self.trades)

    @property
    def no_fills(self) -> int:
        return sum(1 for t in self.trades if t.outcome is Outcome.NO_FILL)

    @property
    def wins(self) -> int:
        return sum(1 for t in self.trades if t.is_win)

    @property
    def losses(self) -> int:
        return sum(1 for t in self.trades if t.is_loss)

    @property
    def timeouts(self) -> int:
        return sum(1 for t in self.trades if t.outcome is Outcome.TIMEOUT)

    # ------------------------------------------------------------------ #
    # Performance — all in R units
    # ------------------------------------------------------------------ #

    @property
    def win_rate(self) -> float:
        """Wins / filled trades (``0.0`` when there are no filled trades)."""
        n = self.num_trades
        return self.wins / n if n else 0.0

    @property
    def total_r(self) -> float:
        """Sum of R-multiples across filled trades (the final equity level)."""
        return sum(t.r_multiple for t in self.filled_trades)

    @property
    def expectancy(self) -> float:
        """Average R per filled trade — the engine's edge per trade."""
        n = self.num_trades
        return self.total_r / n if n else 0.0

    @property
    def average_rr(self) -> float:
        """Average *target* reward:risk across filled trades (the planned RR)."""
        filled = self.filled_trades
        if not filled:
            return 0.0
        return sum(t.entry.realized_rr for t in filled) / len(filled)

    @property
    def gross_profit(self) -> float:
        return sum(t.r_multiple for t in self.filled_trades if t.r_multiple > 0)

    @property
    def gross_loss(self) -> float:
        """Total losing R as a positive number."""
        return -sum(t.r_multiple for t in self.filled_trades if t.r_multiple < 0)

    @property
    def profit_factor(self) -> float:
        """Gross profit / gross loss. ``inf`` when there are wins but no losses,
        ``0.0`` when there is neither."""
        gl = self.gross_loss
        if gl == 0:
            return float("inf") if self.gross_profit > 0 else 0.0
        return self.gross_profit / gl

    @property
    def max_consecutive_losses(self) -> int:
        """Longest run of consecutive losing trades (timeouts that closed
        negative count as losses for streak purposes)."""
        streak = 0
        worst = 0
        for t in self.filled_trades:
            if t.r_multiple < 0:
                streak += 1
                worst = max(worst, streak)
            else:
                streak = 0
        return worst

    @property
    def equity_curve(self) -> pd.Series:
        """Cumulative R over filled trades, in trade order, as a pandas Series."""
        running = 0.0
        points: List[float] = []
        for t in self.filled_trades:
            running += t.r_multiple
            points.append(running)
        return pd.Series(points, dtype=float, name="equity_r")

    # ------------------------------------------------------------------ #
    # Reporting
    # ------------------------------------------------------------------ #

    def summary(self) -> str:
        """A readable multi-line summary of the backtest."""
        pf = self.profit_factor
        pf_str = "inf" if pf == float("inf") else f"{pf:.2f}"
        lines = [
            "MMC backtest result",
            "-------------------",
            f"signals processed : {self.num_signals}",
            f"trades (filled)   : {self.num_trades}",
            f"no-fills          : {self.no_fills}",
            f"wins / losses     : {self.wins} / {self.losses}",
            f"timeouts          : {self.timeouts}",
            f"win rate          : {self.win_rate:.1%}",
            f"expectancy (R)    : {self.expectancy:+.3f}",
            f"total (R)         : {self.total_r:+.3f}",
            f"average RR        : {self.average_rr:.2f}",
            f"profit factor     : {pf_str}",
            f"max consec losses : {self.max_consecutive_losses}",
        ]
        return "\n".join(lines)

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.summary()

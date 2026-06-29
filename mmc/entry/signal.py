"""The :class:`Entry` (trade signal) dataclass and trade-management helpers
(transcript 11 — Entries using Order Flow).

An entry is the easy part: it happens **inside a context area** and is all about
fair value gaps (transcript 11, ~1:54). We enter on an FVG, place the stop loss
**above/below the most recent order flow lag** (~12:46) and target a **1:2 RR**
ideally within the context area (~16:18 / ~23:45).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from mmc.core import Direction, FairValueGap, OrderFlowLag, Zone
from mmc.context import ContextArea

# A small default buffer (as a fraction of the lag swing's distance) so the stop
# sits *beyond* the order flow lag rather than exactly on it.
DEFAULT_SL_BUFFER = 0.0

EntryType = str  # "sharp_turn" | "order_flow"


def make_stop_loss(
    lag: OrderFlowLag,
    direction: Direction,
    buffer: float = DEFAULT_SL_BUFFER,
) -> float:
    """Stop loss **above** (bearish) / **below** (bullish) the most recent order
    flow lag (transcript 11, ~12:46 / ~16:18).

    The reference level is the lag's swing price (the high of the order flow lag
    for a bearish trade, the low for a bullish one). ``buffer`` is an absolute
    price padding placed beyond that level.
    """
    level = lag.swing.price
    if direction is Direction.BEARISH:
        return level + buffer  # stop above the lag high
    return level - buffer      # stop below the lag low


def make_take_profit(entry_price: float, stop_loss: float, rr: float = 2.0) -> float:
    """Take profit at ``rr`` times the risk, in the trade's favour (default 1:2).

    Risk = ``|entry_price - stop_loss|``. For a bearish trade the stop sits above
    entry, so the target sits *below*; for a bullish trade it sits *above*.
    (transcript 11, ~16:18 / ~23:45 — "target a simple one to two RR".)
    """
    risk = abs(entry_price - stop_loss)
    if stop_loss > entry_price:           # stop above entry => bearish => TP below
        return entry_price - rr * risk
    return entry_price + rr * risk        # stop below entry => bullish => TP above


def should_move_to_breakeven(
    entry: "Entry",
    last_lag: Optional[OrderFlowLag] = None,
) -> bool:
    """Stub: move the stop to break even when there's **no reason to return**
    based on order flow (transcript 11, ~24:32 / ~29:32).

    "No reason to return" means the latest order flow lag is itself in context
    (in the trade's direction and beyond the entry), so price has continued and
    a retrace into the entry FVG is no longer expected. A minimal, deterministic
    proxy: a new same-direction lag has formed past the entry FVG towards the
    target.
    """
    if last_lag is None:
        return False
    if last_lag.direction is not entry.direction:
        return False
    # The new lag must sit *past* the entry FVG, in the direction of the trade.
    if entry.direction is Direction.BEARISH:
        return last_lag.fvg.top <= entry.entry_zone.bottom
    return last_lag.fvg.bottom >= entry.entry_zone.top


@dataclass
class Entry:
    """A trade signal generated inside a context area (transcript 11).

    ``direction``    polarity of the trade (matches the context direction).
    ``entry_zone``   the FVG we enter on (the "fair value gap out" for a sharp
                     turn, or the second lag's FVG for an order-flow entry).
    ``stop_loss``    above/below the most recent order flow lag (~12:46).
    ``take_profit``  a 1:2 RR by default (~16:18).
    ``rr``           the risk:reward multiple used (default 2.0).
    ``context``      the :class:`~mmc.context.ContextArea` this entry sits in.
    ``entry_type``   "sharp_turn" or "order_flow".
    ``index``        integer bar position the entry is confirmed at (the entry
                     FVG's 3rd candle).
    ``lag``          the most recent order flow lag the stop is anchored to.
    ``bars_to_turn`` (sharp turn only) bars between the FVG-in and FVG-out —
                     fewer = faster = higher quality (~13:06).
    ``fast``         convenience flag: a "fast" sharp turn (few bars).
    """

    direction: Direction
    entry_zone: FairValueGap
    stop_loss: float
    take_profit: float
    context: ContextArea
    entry_type: EntryType
    index: int
    lag: Optional[OrderFlowLag] = None
    rr: float = 2.0
    bars_to_turn: Optional[int] = None
    fast: bool = False

    # ------------------------------------------------------------------ #
    # Convenience
    # ------------------------------------------------------------------ #

    @property
    def entry_price(self) -> float:
        """The price we enter at — the near edge of the entry FVG in the trade's
        favour (the FVG top for a bearish entry, the bottom for a bullish one)."""
        if self.direction is Direction.BEARISH:
            return self.entry_zone.top
        return self.entry_zone.bottom

    @property
    def risk(self) -> float:
        """Distance from entry to stop (always positive)."""
        return abs(self.entry_price - self.stop_loss)

    @property
    def reward(self) -> float:
        """Distance from entry to target (always positive)."""
        return abs(self.take_profit - self.entry_price)

    @property
    def realized_rr(self) -> float:
        """Actual reward/risk ratio of this entry (should equal ``rr``)."""
        if self.risk == 0:
            return 0.0
        return self.reward / self.risk

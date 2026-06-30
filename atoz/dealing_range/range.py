"""Dealing Ranges + premium / discount / equilibrium (A-Z Guide ep 21).

Ep 21 ("Full Trading Plan using Dealing Ranges") defines a dealing range
**mechanically**:

> "a dealing range is a range that took out buy side liquidity and then it took
> out sell side or vice versa it took out sell side liquidity and then buy side
> liquidity ... Buy side liquidity is swing highs. Sell side liquidity is swing
> lows."

So: a range bounded by a swing high and a swing low where price **took out one
side and then the other** (high-then-low ⇒ bearish dealing range; low-then-high
⇒ bullish). "Took out" = traded beyond that swing level.

Premium / discount (ep 21, and ep 1/2 PD arrays):
> "price moves from premium to discount and from discount to premium ... we want
> to enter at the low of that dealing range (if it's a bearish dealing range)"

Premium = upper half of the range (> 0.5), discount = lower half (< 0.5),
equilibrium = exactly the 0.5 midpoint.

Optional FVG rule (ep 21):
> "what if we add the rule the dealing range has to have a bullish fair value
> gap for a bullish dealing range we have to have a bullish fair value gap"

Trade construction (ep 21):
> "we want to enter at the low of that dealing range ... you place your stop
> above the dealing range ... and you target the target we had established on the
> daily time frame (the opposing daily discount array)" (mirror for bullish).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import pandas as pd

from atoz.core import (
    Candles,
    Direction,
    FVG,
    Swing,
    SwingType,
    find_fvgs,
    find_swings,
    swing_highs,
    swing_lows,
)


class PriceZone(Enum):
    """Where a price sits inside a dealing range (ep 21 / ep 1-2)."""

    PREMIUM = "premium"          # > 0.5  — sell side, a premium array
    DISCOUNT = "discount"        # < 0.5  — buy side, a discount array
    EQUILIBRIUM = "equilibrium"  # == 0.5 (within tolerance)


@dataclass
class DealingRange:
    """A dealing range (ep 21): high↔low that swept buy-side then sell-side
    liquidity (or vice versa).

    - ``high`` / ``low`` : the buy-side (swing high) and sell-side (swing low)
      levels that were taken.
    - ``high_index`` / ``low_index`` : bar positions of those swings.
    - ``direction`` : BEARISH if buy-side was taken first then sell-side
      (high→low delivery, a bearish dealing range); BULLISH for low→high.
    - ``index`` : bar position where the range completed (the later sweep).
    - ``fvg`` : the qualifying same-direction FVG inside the range, if the FVG
      rule was applied.
    """

    high: float
    low: float
    high_index: int
    low_index: int
    direction: Direction
    index: int
    fvg: Optional[FVG] = None

    @property
    def size(self) -> float:
        return self.high - self.low

    @property
    def equilibrium(self) -> float:
        """The 0.5 / 50% level (ep 21 equilibrium)."""
        return (self.high + self.low) / 2.0

    def fib(self, price: float) -> float:
        """Normalize a price to [0,1] within the range (0 = low, 1 = high)."""
        if self.size == 0:
            return 0.5
        return (price - self.low) / self.size

    def classify(self, price: float, tolerance: float = 1e-9) -> PriceZone:
        """Premium (>0.5) / discount (<0.5) / equilibrium (==0.5) of ``price``."""
        f = self.fib(price)
        if abs(f - 0.5) <= tolerance:
            return PriceZone.EQUILIBRIUM
        return PriceZone.PREMIUM if f > 0.5 else PriceZone.DISCOUNT

    @property
    def entry(self) -> float:
        """The dealing-range entry level (ep 21): the *low* of a bearish dealing
        range, the *high* of a bullish one — i.e. enter from the discount/premium
        extreme matching the intended continuation."""
        return self.low if self.direction is Direction.BEARISH else self.high

    @property
    def stop(self) -> float:
        """Stop placement (ep 21): "above the dealing range high" for a bearish
        range; below the low for a bullish range."""
        return self.high if self.direction is Direction.BEARISH else self.low


def find_dealing_ranges(
    df: pd.DataFrame,
    swings: Optional[List[Swing]] = None,
    require_fvg: bool = False,
) -> List[DealingRange]:
    """Detect all dealing ranges (ep 21).

    A dealing range forms when consecutive opposite-side liquidity is taken:
    a swing high is taken out, then a swing low (bearish range), or a swing low
    then a swing high (bullish range). "Taken out" = a later bar trades beyond
    the swing level.

    Mechanics:
      1. Get swing highs (buy-side) and swing lows (sell-side).
      2. Walk swings in time order. When a swing is *taken* (price trades beyond
         it) and the immediately prior taken swing was the opposite kind, the
         pair bounds a dealing range; direction follows which side was taken
         second (sell-side second ⇒ bearish, buy-side second ⇒ bullish).
      3. ``require_fvg`` (ep 21 optional rule): keep only ranges that contain a
         same-direction FVG between the two swept swings.

    Returns ranges ordered by completion bar.
    """
    if swings is None:
        swings = find_swings(df)

    c = Candles.of(df)
    highs = swing_highs(swings)
    lows = swing_lows(swings)

    # For each swing, find the first later bar that takes it out.
    taken: List[tuple] = []  # (take_bar, swing)
    for s in highs:
        tb = _first_break(c, s.index, s.price, above=True)
        if tb is not None:
            taken.append((tb, s))
    for s in lows:
        tb = _first_break(c, s.index, s.price, above=False)
        if tb is not None:
            taken.append((tb, s))

    # Order sweeps by the bar at which each side was taken.
    taken.sort(key=lambda t: t[0])

    fvgs = find_fvgs(df) if require_fvg else []
    ranges: List[DealingRange] = []

    prev = None
    for take_bar, swing in taken:
        if prev is not None and prev[1].kind is not swing.kind:
            prev_swing = prev[1]
            # Direction = which side was taken *second* (this one).
            if swing.kind is SwingType.LOW:
                # sell-side taken second ⇒ bearish dealing range
                direction = Direction.BEARISH
                high = prev_swing.price
                low = swing.price
                high_index = prev_swing.index
                low_index = swing.index
            else:
                # buy-side taken second ⇒ bullish dealing range
                direction = Direction.BULLISH
                high = swing.price
                low = prev_swing.price
                high_index = swing.index
                low_index = prev_swing.index

            dr = DealingRange(
                high=high,
                low=low,
                high_index=high_index,
                low_index=low_index,
                direction=direction,
                index=take_bar,
            )

            if require_fvg:
                match = _qualifying_fvg(dr, fvgs)
                if match is None:
                    prev = (take_bar, swing)
                    continue
                dr.fvg = match

            ranges.append(dr)
        prev = (take_bar, swing)

    ranges.sort(key=lambda r: r.index)
    return ranges


def _first_break(c: Candles, after_index: int, level: float, above: bool) -> Optional[int]:
    """First bar after ``after_index`` whose extreme trades beyond ``level``."""
    for k in range(after_index + 1, c.n):
        if above and c.high[k] > level:
            return k
        if not above and c.low[k] < level:
            return k
    return None


def _qualifying_fvg(dr: DealingRange, fvgs: List[FVG]) -> Optional[FVG]:
    """First same-direction FVG whose middle bar falls between the two swept
    swings and whose body sits inside the range (ep 21 FVG rule)."""
    lo_bar = min(dr.high_index, dr.low_index)
    hi_bar = max(dr.high_index, dr.low_index)
    for fvg in fvgs:
        if fvg.direction is not dr.direction:
            continue
        if lo_bar <= fvg.index <= hi_bar:
            if fvg.bottom >= dr.low and fvg.top <= dr.high:
                return fvg
    return None

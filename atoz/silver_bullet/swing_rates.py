"""Swing rates — the Fibonacci guideline for entry levels (A-Z Guide ep 33).

> "if we draw our fibonacci tool from the intermediate term high to the target
> aka the intermediate term low then these are your swing rates we have zero we
> have 0.25 0.5 aka your equilibrium then we have 0.75 and then we have one and
> one is your terminus. terminus meaning your target. your draw on liquidity."
>   — ep 33

Each level has a *mechanical character* the instructor assigns:

  * **0.25** — first / early ST entry ("a very early entry").
  * **0.5**  — *equilibrium* ("not in premium and not in discount"): expect
               consolidation, a liquidity sweep, and an entry — the **biggest
               retracement** ("way more candles ... a bigger retracement").
  * **0.75** — the **Silver Bullet** level: *close to the drawn liquidity*, so
               you do **not** expect a huge retracement, only "a sting into a
               fair value gap" before continuing to the target.

The fib is always drawn *in context*: ITH→ITL for shorts, ITL→ITH for longs
("you always draw it in the right context").
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List

import pandas as pd

from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Candles, Direction, Swing, SwingType


class SwingRate(Enum):
    """The five fib swing-rate levels (ep 33)."""

    ZERO = 0.0
    QUARTER = 0.25
    EQUILIBRIUM = 0.5
    THREE_QUARTER = 0.75      # the Silver Bullet level
    TERMINUS = 1.0            # the target / draw on liquidity

    @property
    def is_silver_bullet(self) -> bool:
        return self is SwingRate.THREE_QUARTER


@dataclass
class TermRange:
    """An intermediate-term range = the *context* for swing rates (ep 33/31).

    For a bearish context we sell from the intermediate-term **high** down to the
    intermediate-term **low** (the target / draw on liquidity). ``high`` and
    ``low`` are absolute prices; ``high_index`` / ``low_index`` are bar
    positions; ``direction`` is the move toward the target.
    """

    high: float
    low: float
    high_index: int
    low_index: int
    direction: Direction      # BEARISH: target = low; BULLISH: target = high

    @property
    def target(self) -> float:
        """The terminus (1.0) — the draw on liquidity (ep 33)."""
        return self.low if self.direction is Direction.BEARISH else self.high

    @property
    def origin(self) -> float:
        """The 0.0 anchor (the swing we draw the fib *from*)."""
        return self.high if self.direction is Direction.BEARISH else self.low

    @property
    def origin_index(self) -> int:
        return self.high_index if self.direction is Direction.BEARISH else self.low_index

    @property
    def target_index(self) -> int:
        return self.low_index if self.direction is Direction.BEARISH else self.high_index

    def price_at(self, rate: float) -> float:
        """Price at a swing-rate fraction (0.0 = origin, 1.0 = target)."""
        return self.origin + (self.target - self.origin) * rate

    def levels(self) -> Dict[SwingRate, float]:
        """The five swing-rate prices, drawn in context (ep 33)."""
        return {r: self.price_at(r.value) for r in SwingRate}

    def crossed(self, price: float, rate: float) -> bool:
        """True once ``price`` has reached/crossed a swing-rate level.

        > "when I say we are trading into that level if we just cross that
        > level so we just trade below it ... if we just cross that line then
        > that's exactly when you can expect some kind of entry."  — ep 33

        For a bearish range price moves *down* through levels, so a level is
        crossed once price trades at-or-below it; mirror for bullish.
        """
        lvl = self.price_at(rate)
        if self.direction is Direction.BEARISH:
            return price <= lvl
        return price >= lvl


def find_term_ranges(
    df: pd.DataFrame,
    swings: List[Swing] | None = None,
    strength: int = 2,
) -> List[TermRange]:
    """Build candidate intermediate-term ranges from consecutive opposing swings.

    The transcript treats *the* intermediate-term high→low (or low→high) as the
    context. Mechanically, every adjacent (high, low) pair where the high
    precedes the low is a bearish context (sell to the low); every (low, high)
    pair is a bullish context. We return them all, newest last, so a detector
    can pick the most recent / relevant.
    """
    if swings is None:
        swings = find_swings(df, strength=strength)
    ordered = sorted(swings, key=lambda s: s.index)

    out: List[TermRange] = []
    for a, b in zip(ordered, ordered[1:]):
        if a.kind is SwingType.HIGH and b.kind is SwingType.LOW and a.price > b.price:
            out.append(TermRange(a.price, b.price, a.index, b.index, Direction.BEARISH))
        elif a.kind is SwingType.LOW and b.kind is SwingType.HIGH and b.price > a.price:
            out.append(TermRange(a.price, b.price, a.index, b.index, Direction.BULLISH))
    return out

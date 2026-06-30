"""DOL via Fibonacci — swing projections (A-Z Guide ep 20).

Ep 20 ("know DOL using Fibonacci") teaches how to project where price will
likely *Draw On Liquidity* (DOL) by drawing a Fibonacci over the **manipulation
part of the power-of-three (the Judas swing)** and reading the negative
extensions as targets.

Transcript — the exact mechanical recipe
----------------------------------------
> "this judas swing this manipulation part you would take your fibonacci right
> there you draw it from that swing low right there to that swing high ... Then
> the Fibonacci settings are 1 to 0. In between that, you have nothing. But on
> the minus side, you have minus 0.27 minus 0.62 minus 1 a symmetrical swing
> point ... minus 1.62 and minus to [minus 2] a double symmetrical swing point.
> these levels is what price can reach for"

So the fib is anchored 1 → 0 over the Judas/manipulation leg and the **negative
side** carries the projection levels (the DOL targets):

    -0.27, -0.62, -1.0 (symmetrical swing point), -1.62, -2.0 (double sym.)

Wick-vs-body choice (volatility):
> "i am now drawing it from the bodies to the bodies not using the wicks here
> and the reason for that is very much based off of volatility ... play around
> with it ... see which one of them is more aligning with premium or discount
> arrays"

Standard deviations (indices / futures):
> "for the indices ... you don't use the same swing projection you use standard
> deviations ... it's constantly 0.5 0.5 added onto that minus 1 0.5 added onto
> that minus 1.5 and it stops at minus 3 ... because futures in general indices
> are way more volatile"

So for futures/indices the projection side is the half-steps:

    -1.0, -1.5, -2.0, -2.5, -3.0

FAITHFULNESS CAVEAT
-------------------
Mid-video the instructor corrects himself:
> "the minus 0.62 ... that one is supposed to be 0.68. I messed it up with my
> Fibonacci settings ... It is supposed to be 0.68."
He then continues to *speak of and use* the -0.62 level for the rest of the
episode. We therefore expose -0.62 as the default (what he actually uses on the
charts) and provide ``DOL_LEVELS_CORRECTED`` (with -0.68) so the caller can opt
into the correction he intended. Nothing here is a proxy: both are the literal
numbers he states.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import pandas as pd

from atoz.core import Candles, Direction, Swing, SwingType


# --------------------------------------------------------------------------- #
# The fib level menus exactly as the instructor states them
# --------------------------------------------------------------------------- #

#: Negative-extension projection levels for FX measured-swing projections,
#: as the instructor *uses* them on the charts (ep 20).
DOL_LEVELS: List[float] = [-0.27, -0.62, -1.0, -1.62, -2.0]

#: Same menu but honoring the instructor's mid-video correction
#: ("the -0.62 ... is supposed to be 0.68").
DOL_LEVELS_CORRECTED: List[float] = [-0.27, -0.68, -1.0, -1.62, -2.0]

#: Standard-deviation projection levels for indices / futures (ep 20):
#: 0.5 increments from -1.0 down to -3.0.
STD_DEV_LEVELS: List[float] = [-1.0, -1.5, -2.0, -2.5, -3.0]

#: Human names the instructor attaches to the round projection levels.
LEVEL_NAMES: Dict[float, str] = {
    -1.0: "symmetrical swing point",
    -2.0: "double symmetrical swing point",
}


class AnchorMode(Enum):
    """Whether the fib is drawn wick-to-wick or body-to-body (ep 20 — the
    volatility choice: "play around with it ... see which one is more aligning
    with premium or discount arrays")."""

    WICK = "wick"
    BODY = "body"


class ProjectionStyle(Enum):
    """Which level menu to project with (ep 20)."""

    MEASURED = "measured"        # FX measured-swing projections (DOL_LEVELS)
    STANDARD_DEVIATION = "std"   # indices / futures (STD_DEV_LEVELS)


@dataclass
class FibLevel:
    """One projected fib level and its price."""

    ratio: float
    price: float
    name: str = ""

    @property
    def is_projection(self) -> bool:
        """Negative ratios are the DOL projection (target) side."""
        return self.ratio < 0.0


@dataclass
class SwingProjection:
    """A Fibonacci drawn over a Judas/manipulation leg (ep 20).

    Anchors:
        ``anchor_zero`` is the fib's 0 level (end of the manipulation leg — the
        swing it terminates at), ``anchor_one`` is the fib's 1 level (start of
        the leg). The negative extensions project beyond ``anchor_zero`` and are
        the DOL targets.

    For a BEARISH projection (drawn high→low: 1 at the high, 0 at the low) the
    negative levels sit *below* the low — the draw on sell-side liquidity.
    For a BULLISH projection (drawn low→high) they sit *above* the high.
    """

    direction: Direction
    anchor_one: float          # fib 1.0 (start of manipulation leg)
    anchor_zero: float         # fib 0.0 (end of manipulation leg)
    one_index: int
    zero_index: int
    mode: AnchorMode
    style: ProjectionStyle
    levels: List[FibLevel] = field(default_factory=list)

    @property
    def equilibrium(self) -> float:
        """The 0.5 level of the drawn leg (ep 21 equilibrium / 50%)."""
        return (self.anchor_one + self.anchor_zero) / 2.0

    def projections(self) -> List[FibLevel]:
        """Only the negative-extension DOL target levels."""
        return [lv for lv in self.levels if lv.is_projection]

    def price_at(self, ratio: float) -> float:
        """Price of an arbitrary fib ratio (1.0 → anchor_one, 0.0 → anchor_zero,
        negative → projection)."""
        span = self.anchor_one - self.anchor_zero
        return self.anchor_zero + ratio * span


def project_swing(
    swing_a: Swing,
    swing_b: Swing,
    df: Optional[pd.DataFrame] = None,
    mode: AnchorMode = AnchorMode.WICK,
    style: ProjectionStyle = ProjectionStyle.MEASURED,
    levels: Optional[List[float]] = None,
) -> SwingProjection:
    """Draw a Fibonacci over the manipulation (Judas) leg ``swing_a → swing_b``.

    Per ep 20 you draw "from that swing low ... to that swing high" (bullish) or
    high→low (bearish). The **fib 1** sits at the *start* of the leg
    (``swing_a``) and **fib 0** at the *end* (``swing_b``); the negative
    extensions beyond fib 0 are the DOL targets.

    - ``swing_a`` / ``swing_b`` : the two swings bounding the manipulation leg,
      in draw order. A bearish projection draws HIGH→LOW; bullish draws LOW→HIGH.
    - ``mode`` : WICK uses swing prices; BODY uses candle bodies at the swing
      bars (requires ``df``) — the ep-20 volatility choice.
    - ``style`` : MEASURED (FX) or STANDARD_DEVIATION (indices/futures).
    - ``levels`` : override the projection menu (e.g. ``DOL_LEVELS_CORRECTED``).

    Direction is inferred from the swing kinds: low→high ⇒ BULLISH projection
    (targets above), high→low ⇒ BEARISH (targets below).
    """
    direction = (
        Direction.BULLISH
        if (swing_a.kind is SwingType.LOW and swing_b.kind is SwingType.HIGH)
        else Direction.BEARISH
    )

    anchor_one = _anchor_price(swing_a, df, mode, is_zero=False, direction=direction)
    anchor_zero = _anchor_price(swing_b, df, mode, is_zero=True, direction=direction)

    if levels is None:
        levels = STD_DEV_LEVELS if style is ProjectionStyle.STANDARD_DEVIATION else DOL_LEVELS

    span = anchor_one - anchor_zero
    fib_levels = [
        FibLevel(ratio=r, price=anchor_zero + r * span, name=LEVEL_NAMES.get(r, ""))
        for r in levels
    ]

    return SwingProjection(
        direction=direction,
        anchor_one=anchor_one,
        anchor_zero=anchor_zero,
        one_index=swing_a.index,
        zero_index=swing_b.index,
        mode=mode,
        style=style,
        levels=fib_levels,
    )


def _anchor_price(
    swing: Swing,
    df: Optional[pd.DataFrame],
    mode: AnchorMode,
    is_zero: bool,
    direction: Direction,
) -> float:
    """Resolve the fib anchor price for a swing under WICK vs BODY mode."""
    if mode is AnchorMode.WICK or df is None:
        return swing.price

    c = Candles.of(df)
    i = swing.index
    # Body anchoring (ep 20): use the body edge that faces the leg.
    if swing.kind is SwingType.HIGH:
        return c.body_top(i)
    return c.body_bottom(i)

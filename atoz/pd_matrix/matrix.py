"""PD Array Matrix — FLOD / LLOD (A-Z Guide ep 9).

> A **price-action lag** is a swing-high-to-swing-low impulse leg. Inside it,
> all same-polarity PD arrays form the **PD array matrix**. The **FLOD** (first
> line of defense) is the first array a retracement hits — 9/10 times an FVG,
> and high-probability when it *overlaps* another array. The **LLOD** (last line
> of defense) is the swing itself, which should not be invalidated (a liquidity
> pool beyond it is allowed, but price shouldn't *stay* beyond).  — ep 9

This collects every block / FVG inside a lag, picks the FLOD (nearest to the
entering side) and LLOD (the originating swing), and scores the FLOD by overlap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from atoz.blocks import PDArray, find_all_blocks
from atoz.core.fvg import FVG, find_fvgs
from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Direction, Swing, Zone


@dataclass
class PriceActionLag:
    """A swing→swing impulse leg and the PD arrays inside it (ep 9)."""

    direction: Direction          # BEARISH lag = retrace up into premium arrays
    start: Swing                  # the origin swing (becomes the LLOD)
    end: Swing                    # the opposing swing
    arrays: List[Zone] = field(default_factory=list)   # PD arrays inside the lag
    flod: Optional[Zone] = None   # first line of defense
    llod_price: float = 0.0       # last line of defense (the origin swing price)
    flod_overlaps: int = 0        # how many other arrays overlap the FLOD

    @property
    def high_probability(self) -> bool:
        """High prob when the FLOD overlaps ≥1 other array (ep 9)."""
        return self.flod is not None and self.flod_overlaps >= 1


def find_price_action_lags(
    df: pd.DataFrame,
    swings: Optional[List[Swing]] = None,
) -> List[PriceActionLag]:
    """Build price-action lags from consecutive opposing swings and populate the
    PD-array matrix, FLOD and LLOD for each (ep 9)."""
    if swings is None:
        swings = find_swings(df)
    blocks = find_all_blocks(df)
    fvgs = find_fvgs(df)

    lags: List[PriceActionLag] = []
    ordered = sorted(swings, key=lambda s: s.index)

    for a, b in zip(ordered, ordered[1:]):
        if a.kind is b.kind:
            continue  # need an opposing pair (high→low or low→high)
        # A bearish lag falls from a high to a low; we retrace UP into premium.
        bearish = a.price > b.price
        direction = Direction.BEARISH if bearish else Direction.BULLISH
        top = max(a.price, b.price)
        bottom = min(a.price, b.price)

        # PD arrays of the lag's polarity that sit inside the leg's price band.
        inside: List[Zone] = []
        for z in list(blocks) + list(fvgs):
            if getattr(z, "direction", None) is not direction:
                continue
            if a.index <= z.index <= b.index and z.bottom >= bottom and z.top <= top:
                inside.append(z)
        if not inside:
            continue

        # FLOD = the array nearest the entering side (top for bearish retrace-up,
        # bottom for bullish retrace-down).
        if bearish:
            flod = min(inside, key=lambda z: top - z.top)   # highest array
        else:
            flod = min(inside, key=lambda z: z.bottom - bottom)  # lowest array

        overlaps = sum(
            1 for z in inside if z is not flod and z.bottom <= flod.top and z.top >= flod.bottom
        )

        lags.append(
            PriceActionLag(
                direction=direction, start=a, end=b, arrays=inside,
                flod=flod, llod_price=a.price, flod_overlaps=overlaps,
            )
        )

    return lags

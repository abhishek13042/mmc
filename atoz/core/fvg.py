"""Fair Value Gaps — used throughout the A-Z blocks as the "overlapping" PD array
that strengthens a block (ep 2-6 all reference "overlapping with a fair value
gap"). Full FVG/BISI/SIBI treatment is ep 8; this is the minimal detector the
block layer needs.

A bullish FVG (BISI — buy-side imbalance sell-side inefficiency): a 3-candle gap
where candle-1 high < candle-3 low. A bearish FVG (SIBI): candle-1 low >
candle-3 high.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from .types import Candles, Direction, Zone


@dataclass
class FVG(Zone):
    """A fair value gap (a 3-candle imbalance). ``index`` is the middle candle."""

    c1_index: int = 0
    c3_index: int = 0


def find_fvgs(df: pd.DataFrame) -> List[FVG]:
    """Return all 3-candle fair value gaps, ordered by middle-candle index."""
    c = Candles.of(df)
    out: List[FVG] = []

    for i in range(1, c.n - 1):
        # bullish: gap between candle i-1 high and candle i+1 low
        if c.high[i - 1] < c.low[i + 1]:
            out.append(
                FVG(
                    top=float(c.low[i + 1]),
                    bottom=float(c.high[i - 1]),
                    index=i,
                    direction=Direction.BULLISH,
                    c1_index=i - 1,
                    c3_index=i + 1,
                )
            )
        # bearish: gap between candle i-1 low and candle i+1 high
        elif c.low[i - 1] > c.high[i + 1]:
            out.append(
                FVG(
                    top=float(c.low[i - 1]),
                    bottom=float(c.high[i + 1]),
                    index=i,
                    direction=Direction.BEARISH,
                    c1_index=i - 1,
                    c3_index=i + 1,
                )
            )

    return out

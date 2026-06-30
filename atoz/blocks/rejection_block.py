"""Rejection Blocks (A-Z Guide ep 4, transcript 005).

> A rejection block is a candle with a **long wick**. Price sweeps the *bodies*
> but not the full wick, then reverses. Bearish: take the **highest candle**
> (its body high) — price trades above the body but not above the wick, then
> drops. Bullish: the **lowest candle** (its body low). Best when the wick is
> long, on the *outside* (a swing extreme), and counter-trend.  — ep 4

The "block" level is the body extreme (open/close), not the wick — the wick is
"purely for manipulation", the liquidity sits above/below the bodies.
"""

from __future__ import annotations

from typing import List

import pandas as pd

from atoz.core.types import Candles, Direction

from .types import BlockType, PDArray

# A wick counts as "long" when it is at least this multiple of the body.
_LONG_WICK_RATIO = 1.5
# Look-back / forward for the "outside / swing extreme" check.
_EXTREME_WINDOW = 5


def find_rejection_blocks(df: pd.DataFrame, long_wick_ratio: float = _LONG_WICK_RATIO) -> List[PDArray]:
    """Detect bullish and bearish rejection blocks (long-wick rejections, ep 5)."""
    c = Candles.of(df)
    out: List[PDArray] = []

    for i in range(_EXTREME_WINDOW, c.n - _EXTREME_WINDOW):
        body_top = c.body_top(i)
        body_bottom = c.body_bottom(i)
        body = max(body_top - body_bottom, 1e-9)
        upper_wick = c.high[i] - body_top
        lower_wick = body_bottom - c.low[i]

        lo = i - _EXTREME_WINDOW
        hi = i + _EXTREME_WINDOW + 1

        # Bearish: long upper wick, candle is the local high (outside / extreme)
        if upper_wick >= long_wick_ratio * body and c.high[i] >= c.high[lo:hi].max():
            out.append(
                PDArray(
                    top=float(c.high[i]),          # zone spans body-high → wick-high
                    bottom=float(body_top),         # the body high is the level
                    index=i, direction=Direction.BEARISH,
                    block_type=BlockType.REJECTION,
                    mean_threshold=float(body_top),
                    formed_index=i,
                )
            )

        # Bullish: long lower wick, candle is the local low (outside / extreme)
        if lower_wick >= long_wick_ratio * body and c.low[i] <= c.low[lo:hi].min():
            out.append(
                PDArray(
                    top=float(body_bottom),         # the body low is the level
                    bottom=float(c.low[i]),         # zone spans wick-low → body-low
                    index=i, direction=Direction.BULLISH,
                    block_type=BlockType.REJECTION,
                    mean_threshold=float(body_bottom),
                    formed_index=i,
                )
            )

    out.sort(key=lambda b: b.index)
    return out

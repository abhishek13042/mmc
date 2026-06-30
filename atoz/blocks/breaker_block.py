"""Breaker Blocks (A-Z Guide ep 3, transcript 004).

> The **breaker pattern** takes out *both* a swing high and a swing low, then
> price moves back into the block. Bearish: ...up, down, up takes the high, down
> takes the low, return into the low of the bearish (down) candle, continue
> lower. As soon as price wicks the second level the breaker is confirmed.
> A breaker + overlapping FVG is the "unicorn setup".  — ep 3

A breaker and a mitigation block are often confused: the mitigation block is a
*swing failure* (a swing that *fails* to take the prior), the breaker *succeeds*
in taking out both sides (ep 2/3 — "the only two reversal patterns").

Detection (v1, faithful to the reversal-origin reading):
    bullish: swing high SH, then a later swing low SL that is swept; price then
             trades back above SH (both levels taken). Block = the SL candle;
             trade from it back up.
    bearish: swing low SL, then a later swing high SH that is swept; price then
             trades back below SL. Block = the SH candle.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Candles, Direction, Swing, SwingType

from .types import BlockType, PDArray

_CONFIRM_WINDOW = 15


def find_breaker_blocks(df: pd.DataFrame, swings: Optional[List[Swing]] = None) -> List[PDArray]:
    """Detect bullish and bearish breaker blocks (breaker pattern, ep 4)."""
    c = Candles.of(df)
    if swings is None:
        swings = find_swings(df)

    out: List[PDArray] = []
    highs = swing_highs(swings)
    lows = swing_lows(swings)

    # Bullish: prior swing high SH, then swing low SL; price takes back above SH.
    for sl in lows:
        prior_highs = [h for h in highs if h.index < sl.index]
        if not prior_highs:
            continue
        sh = prior_highs[-1]
        broke = None
        for k in range(sl.index + 1, min(c.n, sl.index + 1 + _CONFIRM_WINDOW)):
            if c.high[k] > sh.price:  # takes out the swing high → breaker confirmed
                broke = k
                break
        if broke is None:
            continue
        idx = sl.index
        out.append(
            PDArray(
                top=float(c.body_top(idx)), bottom=float(c.low[idx]),
                index=idx, direction=Direction.BULLISH,
                block_type=BlockType.BREAKER,
                mean_threshold=(float(c.body_top(idx)) + float(c.low[idx])) / 2.0,
                formed_index=broke,
            )
        )

    # Bearish: prior swing low SL, then swing high SH; price takes back below SL.
    for sh in highs:
        prior_lows = [l for l in lows if l.index < sh.index]
        if not prior_lows:
            continue
        sl = prior_lows[-1]
        broke = None
        for k in range(sh.index + 1, min(c.n, sh.index + 1 + _CONFIRM_WINDOW)):
            if c.low[k] < sl.price:  # takes out the swing low → breaker confirmed
                broke = k
                break
        if broke is None:
            continue
        idx = sh.index
        out.append(
            PDArray(
                top=float(c.high[idx]), bottom=float(c.body_bottom(idx)),
                index=idx, direction=Direction.BEARISH,
                block_type=BlockType.BREAKER,
                mean_threshold=(float(c.high[idx]) + float(c.body_bottom(idx))) / 2.0,
                formed_index=broke,
            )
        )

    out.sort(key=lambda b: b.index)
    return out

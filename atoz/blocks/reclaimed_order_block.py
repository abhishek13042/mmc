"""Reclaimed Order Blocks (A-Z Guide ep 5, transcript 006).

> Based on the market-maker model's two curves (a sell curve then a buy curve).
> Order blocks form on the *first* curve; once price trades *through* them
> (wick OR body — "whether it's a wick or body, once we are trading below it,
> then it becomes a reclaimed order block") and is on the other side, they are
> **reclaimed** and hold from that side. A bullish OB traded below then
> reclaimed holds as support; a bearish OB traded above then reclaimed holds
> as resistance. Only worth using when **overlapping** other PD arrays —
> otherwise the chart is a thousand useless lines.  — ep 5

Detection (v1): start from the ep-1 order blocks. A block is *reclaimed* once
price has traded through it via wick or body (low < ob.bottom for bullish;
high > ob.top for bearish) and then returns into the zone from the opposite
side. The block retains its original polarity.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

from atoz.core.types import Candles, Direction

from .order_block import find_order_blocks
from .types import BlockType, PDArray


def find_reclaimed_order_blocks(
    df: pd.DataFrame,
    order_blocks: Optional[List[PDArray]] = None,
) -> List[PDArray]:
    """Detect reclaimed order blocks (ep 6)."""
    c = Candles.of(df)
    if order_blocks is None:
        order_blocks = find_order_blocks(df)

    out: List[PDArray] = []
    for ob in order_blocks:
        # Ep 5 transcript: "once we are trading below it — whether it's a wick or body —
        # then it becomes a reclaimed order block." A wick trade-through is sufficient.
        through_at = None
        for k in range(ob.formed_index + 1, c.n):
            if ob.is_bullish and c.low[k] < ob.bottom:
                through_at = k
                break
            if not ob.is_bullish and c.high[k] > ob.top:
                through_at = k
                break
        if through_at is None:
            continue

        # ... then price returns into the zone from the other side = reclaimed
        return_at = None
        for k in range(through_at + 1, c.n):
            if ob.is_bullish and c.high[k] >= ob.bottom and c.low[k] <= ob.top:
                return_at = k
                break
            if not ob.is_bullish and c.low[k] <= ob.top and c.high[k] >= ob.bottom:
                return_at = k
                break
        if return_at is None:
            continue

        out.append(
            PDArray(
                top=ob.top, bottom=ob.bottom, index=ob.index,
                direction=ob.direction,
                block_type=BlockType.RECLAIMED,
                mean_threshold=ob.mean_threshold,
                formed_index=return_at,
            )
        )

    out.sort(key=lambda b: b.index)
    return out

"""Order Blocks (A-Z Guide ep 1, transcript 002).

> A bullish order block is a **down candle** (or run of consecutive down
> candles = one block) that comes off support, whose **high gets broken** by a
> displacement up. Bearish is the mirror: an up-candle run whose **low gets
> broken**. Mean threshold = 50% of the bodies.  — ep 1

Detection steps (ep 1):
    1. a run of same-direction candles (the opposite colour to the move),
    2. the run's high (bullish) / low (bearish) is broken within a short window
       (the displacement / "break the high of the down candle"),
    3. the run sits at a local support (bullish) / resistance (bearish).

The *return* and mean-threshold respect are entry-time qualities, not detection
requirements ("only support/resistance and the high/low ... have to happen" —
ep 1).
"""

from __future__ import annotations

from typing import List

import pandas as pd

from atoz.core.types import Candles, Direction

from .types import BlockType, PDArray

# How many bars after a candle run we allow the displacement break to occur.
_BREAK_WINDOW = 3


def _runs(c: Candles, bullish: bool) -> List[tuple]:
    """Return (start, end) index pairs of consecutive down (bullish OB) or up
    (bearish OB) candle runs."""
    runs = []
    i = 0
    while i < c.n:
        match = c.is_down(i) if bullish else c.is_up(i)
        if not match:
            i += 1
            continue
        j = i
        while j + 1 < c.n and (c.is_down(j + 1) if bullish else c.is_up(j + 1)):
            j += 1
        runs.append((i, j))
        i = j + 1
    return runs


def find_order_blocks(df: pd.DataFrame, support_window: int = 5) -> List[PDArray]:
    """Detect bullish and bearish order blocks (ep 2)."""
    c = Candles.of(df)
    out: List[PDArray] = []

    for bullish in (True, False):
        direction = Direction.BULLISH if bullish else Direction.BEARISH
        for start, end in _runs(c, bullish):
            run_high = float(c.high[start : end + 1].max())
            run_low = float(c.low[start : end + 1].min())

            # Step 2: the high (bullish) / low (bearish) is broken soon after.
            broke_at = None
            for k in range(end + 1, min(c.n, end + 1 + _BREAK_WINDOW)):
                if bullish and c.high[k] > run_high:
                    broke_at = k
                    break
                if not bullish and c.low[k] < run_low:
                    broke_at = k
                    break
            if broke_at is None:
                continue

            # Step 3: the run is a local support (bullish) / resistance (bearish).
            lo = max(0, start - support_window)
            if bullish:
                if run_low > float(c.low[lo:start].min()) if start > lo else False:
                    continue
            else:
                if run_high < float(c.high[lo:start].max()) if start > lo else False:
                    continue

            # Mean threshold = 50% of the bodies of the run.
            body_top = float(max(c.body_top(k) for k in range(start, end + 1)))
            body_bottom = float(min(c.body_bottom(k) for k in range(start, end + 1)))
            mt = (body_top + body_bottom) / 2.0

            out.append(
                PDArray(
                    top=run_high,
                    bottom=run_low,
                    index=end,
                    direction=direction,
                    block_type=BlockType.ORDER,
                    mean_threshold=mt,
                    formed_index=broke_at,
                )
            )

    out.sort(key=lambda b: b.index)
    return out

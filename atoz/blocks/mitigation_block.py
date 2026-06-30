"""Mitigation Blocks (A-Z Guide ep 2, transcript 003).

> The pattern is a **Swing Failure Pattern**: a down move, then an up move that
> *fails to take out the prior swing high*, then a rejection lower — that
> creates a (bearish) mitigation block. Bullish is the mirror. We take the low
> (bearish) / high (bullish), and it is strongest when *overlapping* another PD
> array.  — ep 2

Note: "mitigation" refers to traders *mitigating* (unwinding) their orders at
the swing point, NOT to a previously-tapped order block. The structural signal
is the Swing Failure Pattern.

Detection (using swings):
    bearish: swing high H1, then a *lower* swing high H2 (fails to take H1),
             then price trades below the swing low between them (rejection
             confirmed). The block is H2's candle; we trade from its high down.
    bullish: swing low L1, then a *higher* swing low L2 (fails to take L1),
             then price trades above the swing high between them.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Candles, Direction, Swing, SwingType

from .types import BlockType, PDArray

_CONFIRM_WINDOW = 12


def _between_swing(swings: List[Swing], a_idx: int, b_idx: int, kind: SwingType) -> Optional[Swing]:
    """The most extreme opposite swing strictly between bar positions a and b."""
    cands = [s for s in swings if a_idx < s.index < b_idx and s.kind is kind]
    if not cands:
        return None
    if kind is SwingType.LOW:
        return min(cands, key=lambda s: s.price)
    return max(cands, key=lambda s: s.price)


def find_mitigation_blocks(df: pd.DataFrame, swings: Optional[List[Swing]] = None) -> List[PDArray]:
    """Detect bullish and bearish mitigation blocks (swing-failure pattern, ep 3)."""
    c = Candles.of(df)
    if swings is None:
        swings = find_swings(df)

    out: List[PDArray] = []
    highs = swing_highs(swings)
    lows = swing_lows(swings)

    # Bearish: a lower swing high (failed retest) then break of the swing low
    for prev, cur in zip(highs, highs[1:]):
        if cur.price >= prev.price:
            continue  # did not fail — it took out the prior high
        mid_low = _between_swing(swings, prev.index, cur.index, SwingType.LOW)
        if mid_low is None:
            continue
        broke = None
        for k in range(cur.index + 1, min(c.n, cur.index + 1 + _CONFIRM_WINDOW)):
            if c.low[k] < mid_low.price:
                broke = k
                break
        if broke is None:
            continue
        idx = cur.index
        top = float(c.high[idx])
        bottom = float(c.body_bottom(idx))
        out.append(
            PDArray(
                top=top, bottom=bottom, index=idx, direction=Direction.BEARISH,
                block_type=BlockType.MITIGATION,
                mean_threshold=(float(c.body_top(idx)) + bottom) / 2.0,
                formed_index=broke,
            )
        )

    # Bullish: a higher swing low (failed retest) then break of the swing high
    for prev, cur in zip(lows, lows[1:]):
        if cur.price <= prev.price:
            continue
        mid_high = _between_swing(swings, prev.index, cur.index, SwingType.HIGH)
        if mid_high is None:
            continue
        broke = None
        for k in range(cur.index + 1, min(c.n, cur.index + 1 + _CONFIRM_WINDOW)):
            if c.high[k] > mid_high.price:
                broke = k
                break
        if broke is None:
            continue
        idx = cur.index
        bottom = float(c.low[idx])
        top = float(c.body_top(idx))
        out.append(
            PDArray(
                top=top, bottom=bottom, index=idx, direction=Direction.BULLISH,
                block_type=BlockType.MITIGATION,
                mean_threshold=(top + float(c.body_bottom(idx))) / 2.0,
                formed_index=broke,
            )
        )

    out.sort(key=lambda b: b.index)
    return out

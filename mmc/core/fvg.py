"""Fair Value Gap detection and mitigation (transcript 01 / 06).

A bullish FVG is a 3-candle pattern: candle 2 (the *expansion-phase* candle)
closes above candle 1's high, and candle 3 does not trade back into candle 1's
high -> a gap remains between ``candle1.high`` (bottom) and ``candle3.low`` (top).
A bearish FVG is the mirror image.

An FVG can only be traded into **once**; :func:`mark_mitigation` flags the first
bar that trades back into the gap so later layers can drop mitigated gaps.
"""

from __future__ import annotations

from typing import List

import pandas as pd

from .types import Direction, FairValueGap


def find_fvgs(df: pd.DataFrame) -> List[FairValueGap]:
    """Return all FVGs in ``df`` confirmed at candle 3, ordered by index."""
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    n = len(df)
    out: List[FairValueGap] = []

    for i in range(2, n):
        c1, c2, c3 = i - 2, i - 1, i

        # Bullish: expansion candle closes above c1 high; c3 low stays above c1 high.
        if c[c2] > h[c1] and l[c3] > h[c1]:
            out.append(
                FairValueGap(
                    top=float(l[c3]),
                    bottom=float(h[c1]),
                    index=c3,
                    direction=Direction.BULLISH,
                    c1_index=c1,
                    c2_index=c2,
                    c3_index=c3,
                )
            )

        # Bearish: expansion candle closes below c1 low; c3 high stays below c1 low.
        if c[c2] < l[c1] and h[c3] < l[c1]:
            out.append(
                FairValueGap(
                    top=float(l[c1]),
                    bottom=float(h[c3]),
                    index=c3,
                    direction=Direction.BEARISH,
                    c1_index=c1,
                    c2_index=c2,
                    c3_index=c3,
                )
            )

    out.sort(key=lambda f: f.index)
    return out


def mark_mitigation(df: pd.DataFrame, fvgs: List[FairValueGap]) -> List[FairValueGap]:
    """Mutate each FVG in-place, setting ``mitigated`` / ``mitigation_index``.

    A bullish FVG is mitigated by the first later bar whose **low** trades into
    the gap (``low <= top``); a bearish FVG by the first later bar whose **high**
    trades into it (``high >= bottom``). Returns the same list for chaining.
    """
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    n = len(df)

    for fvg in fvgs:
        start = fvg.c3_index + 1
        for j in range(start, n):
            if fvg.direction is Direction.BULLISH:
                if l[j] <= fvg.top:
                    fvg.mitigated = True
                    fvg.mitigation_index = j
                    break
            else:  # bearish
                if h[j] >= fvg.bottom:
                    fvg.mitigated = True
                    fvg.mitigation_index = j
                    break
    return fvgs


def unmitigated(fvgs: List[FairValueGap]) -> List[FairValueGap]:
    """Filter to FVGs that have not been traded into (transcript 06)."""
    return [f for f in fvgs if not f.mitigated]

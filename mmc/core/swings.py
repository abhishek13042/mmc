"""Swing point detection (transcript 01 — PD Arrays / swing points).

A swing high is a 3-candle pattern where the middle candle's high is greater
than the candle directly to its left and right; a swing low is the mirror. A
swing is only *confirmed* once the right candle closes. ``left``/``right`` are
exposed so higher timeframes / different fractality can be requested, but the
MMC default is the 3-candle definition (``left == right == 1``).
"""

from __future__ import annotations

from typing import List

import pandas as pd

from .types import SwingPoint, SwingType


def find_swings(df: pd.DataFrame, left: int = 1, right: int = 1) -> List[SwingPoint]:
    """Return all confirmed swing highs and lows, ordered by bar index.

    Each :class:`SwingPoint` stores the integer position of its middle candle.
    """
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)
    swings: List[SwingPoint] = []

    for i in range(left, n - right):
        h = highs[i]
        is_high = all(h > highs[i - k] for k in range(1, left + 1)) and all(
            h > highs[i + k] for k in range(1, right + 1)
        )
        if is_high:
            swings.append(SwingPoint(index=i, price=float(h), kind=SwingType.HIGH))

        lo = lows[i]
        is_low = all(lo < lows[i - k] for k in range(1, left + 1)) and all(
            lo < lows[i + k] for k in range(1, right + 1)
        )
        if is_low:
            swings.append(SwingPoint(index=i, price=float(lo), kind=SwingType.LOW))

    swings.sort(key=lambda s: s.index)
    return swings


def swing_highs(swings: List[SwingPoint]) -> List[SwingPoint]:
    return [s for s in swings if s.kind is SwingType.HIGH]


def swing_lows(swings: List[SwingPoint]) -> List[SwingPoint]:
    return [s for s in swings if s.kind is SwingType.LOW]

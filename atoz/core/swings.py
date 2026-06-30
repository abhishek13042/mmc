"""Swing highs / lows — the foundation the block patterns are built on.

A swing high (ep 3/4/10) is a candle high that is the local maximum over
``strength`` bars either side; a swing low is the mirror. Swing failure and
breaker patterns are defined in terms of taking (or failing to take) these
swings.
"""

from __future__ import annotations

from typing import List

import pandas as pd

from .types import Candles, Swing, SwingType


def find_swings(df: pd.DataFrame, strength: int = 2) -> List[Swing]:
    """Return all swing highs and lows, ordered by bar index.

    ``strength`` = number of bars on each side that must be lower (for a high) /
    higher (for a low). strength=2 is a 5-bar fractal.
    """
    c = Candles.of(df)
    swings: List[Swing] = []

    for i in range(strength, c.n - strength):
        hi = c.high[i]
        lo = c.low[i]
        is_high = all(c.high[i - k] < hi and c.high[i + k] < hi for k in range(1, strength + 1))
        is_low = all(c.low[i - k] > lo and c.low[i + k] > lo for k in range(1, strength + 1))
        if is_high:
            swings.append(Swing(index=i, price=float(hi), kind=SwingType.HIGH))
        elif is_low:
            swings.append(Swing(index=i, price=float(lo), kind=SwingType.LOW))

    swings.sort(key=lambda s: s.index)
    return swings


def swing_highs(swings: List[Swing]) -> List[Swing]:
    return [s for s in swings if s.kind is SwingType.HIGH]


def swing_lows(swings: List[Swing]) -> List[Swing]:
    return [s for s in swings if s.kind is SwingType.LOW]

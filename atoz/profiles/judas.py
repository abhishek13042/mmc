"""Judas Swing (A-Z Guide ep 19).

> A Judas swing is the **fake move before the real move** — the *manipulation*
> phase of power-of-3. It happens at the start of every session/day/week. Price
> makes a fake push (often against the daily direction), reaching into a FLOD
> (an FVG) or a liquidity pool, then reverses into the real expansion. If there
> is an **FVG in the leg** it likely won't sweep the far liquidity — it taps the
> FVG and goes. Get involved in the **retracement** (the Judas), not the
> expansion. Every timeframe must be in context of the one above it.  — ep 19

Detection: within the opening window of a session, find the extreme against the
HTF/daily direction (the fake), then the reversal back through the session open.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from atoz.core.types import Candles, Direction


@dataclass
class JudasSwing:
    """A session-open fake move and its reversal (ep 19)."""

    direction: Direction        # the *real* (post-judas) direction
    session_start: int
    fake_extreme_index: int     # bar of the manipulation extreme
    fake_extreme_price: float
    reversal_index: int         # bar price reverses back through the open


def find_judas_swing(
    df: pd.DataFrame,
    session_start: int,
    daily_direction: Direction,
    window: int = 12,
) -> Optional[JudasSwing]:
    """Detect a Judas swing in the ``window`` bars after ``session_start``.

    For a bullish daily direction the fake is a push **down** (manipulation
    against the move) that then reverses up through the session-open price; the
    deepest low in the window is the manipulation extreme (ep 19).
    """
    c = Candles.of(df)
    end = min(c.n, session_start + window)
    if session_start >= c.n - 2:
        return None

    open_price = c.open[session_start]
    bullish = daily_direction is Direction.BULLISH

    # manipulation extreme = furthest move against the daily direction
    extreme_idx = session_start
    extreme_val = c.low[session_start] if bullish else c.high[session_start]
    for k in range(session_start, end):
        if bullish and c.low[k] < extreme_val:
            extreme_val, extreme_idx = c.low[k], k
        elif not bullish and c.high[k] > extreme_val:
            extreme_val, extreme_idx = c.high[k], k

    # reversal = first bar after the extreme that trades back through the open
    for k in range(extreme_idx + 1, end):
        if bullish and c.high[k] > open_price:
            return JudasSwing(daily_direction, session_start, extreme_idx, float(extreme_val), k)
        if not bullish and c.low[k] < open_price:
            return JudasSwing(daily_direction, session_start, extreme_idx, float(extreme_val), k)
    return None

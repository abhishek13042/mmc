"""Weekly profiles / TGIF (A-Z Guide ep 15).

> Day characteristics: **Monday** range/consolidation (leaves a daily FVG),
> **Tuesday** stings a premium/discount array → high/low of week, **Wednesday**
> trend, **Thursday** trend but TR/END (careful), **Friday** TGIF — sweeps the
> previous-day (Thursday) low/high then reverts back into the range. You catch
> the weekly range with **one shot, one kill**. Volatility lands on the
> economic-calendar day, in harmony with a PD array hovering above/below.  — ep 15

> Weekly close estimate: a Fib from the week's low to its high — the 0.2–0.3
> region is where price tends to close.  — ep 15

This module labels each trading day's role and detects the TGIF reversal.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pandas as pd


class DayRole(Enum):
    RANGE = "range"        # Monday
    HIGH_LOW = "high_low"  # Tuesday — weekly high/low formed
    TREND = "trend"        # Wednesday / Thursday
    TGIF = "tgif"          # Friday — sweep prev-day extreme, revert
    OTHER = "other"


# Monday=0 … Friday=4
_WEEKDAY_ROLE = {
    0: DayRole.RANGE,
    1: DayRole.HIGH_LOW,
    2: DayRole.TREND,
    3: DayRole.TREND,
    4: DayRole.TGIF,
}


@dataclass
class TGIFSetup:
    """A Friday previous-day-extreme sweep that reverts into the weekly range."""

    day: pd.Timestamp
    direction: str          # "bullish" (swept low, revert up) / "bearish"
    swept_level: float
    revert_index: int


def day_role(timestamp: pd.Timestamp) -> DayRole:
    """The expected weekly-profile role for a timestamp's weekday (ep 15)."""
    return _WEEKDAY_ROLE.get(timestamp.weekday(), DayRole.OTHER)


def weekly_close_estimate(week_low: float, week_high: float, bullish: bool) -> float:
    """Fib 0.25 retrace from the week's extreme — the likely close region (ep 15)."""
    rng = week_high - week_low
    return (week_low + 0.25 * rng) if bullish else (week_high - 0.25 * rng)


def find_tgif_setups(daily_df: pd.DataFrame, revert_frac: float = 0.5) -> List[TGIFSetup]:
    """Detect Friday TGIF reversals on a *daily* DataFrame.

    A bullish TGIF: Friday trades below Thursday's low (sweep) then closes back
    above it (reverts into the range). Bearish is the mirror. ``revert_frac`` is
    unused placeholder for future strength filtering.
    """
    out: List[TGIFSetup] = []
    highs = daily_df["high"].to_numpy()
    lows = daily_df["low"].to_numpy()
    closes = daily_df["close"].to_numpy()
    idx = daily_df.index

    for i in range(1, len(daily_df)):
        if idx[i].weekday() != 4:  # Friday
            continue
        thu_low, thu_high = lows[i - 1], highs[i - 1]
        # bullish TGIF: swept Thursday low, closed back above it
        if lows[i] < thu_low <= closes[i]:
            out.append(TGIFSetup(idx[i], "bullish", float(thu_low), i))
        # bearish TGIF: swept Thursday high, closed back below it
        elif highs[i] > thu_high >= closes[i]:
            out.append(TGIFSetup(idx[i], "bearish", float(thu_high), i))
    return out

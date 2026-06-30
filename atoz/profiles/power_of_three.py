"""Power of 3 / AMD / OHLC-OLHC (A-Z Guide ep 18).

> Power of 3 = **Accumulation, Manipulation, Distribution**. Every candle (and
> every session/day/week/month) opens, then **manipulates** (a wick against the
> intended direction), **accumulates** (the symmetric swing from the
> manipulation extreme back through the open — where you want to get involved),
> then **distributes** (the far wick to the close, taking profit at an opposing
> PD array). A bullish candle is **OLHC** (open-low-high-close), a bearish one
> **OHLC**. Reference the **NY midnight open (00:00)** for the daily; buy below
> the open on bullish days.  — ep 18

Fractal: applies to a session candle, a daily candle, a weekly candle, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd


class CandleShape(Enum):
    OLHC = "olhc"   # open-low-high-close → bullish
    OHLC = "ohlc"   # open-high-low-close → bearish


@dataclass
class PowerOfThree:
    """The AMD decomposition of one (aggregated) candle."""

    shape: CandleShape
    open: float
    high: float
    low: float
    close: float
    manipulation_extreme: float   # the wick against the intended direction
    accumulation_top: float       # symmetric band around the open (above open for bullish)
    accumulation_bottom: float    # … (below open for bearish) — where you want to get involved
    distribution_target: float    # the far wick / close side (profit-taking target)

    @property
    def bullish(self) -> bool:
        return self.shape is CandleShape.OLHC


def decompose(open_: float, high: float, low: float, close: float) -> PowerOfThree:
    """Decompose a single OHLC candle into its AMD phases (ep 18).

    Bullish (close > open): manipulation = the low wick (below open); accumulation
    = the symmetric band [open-(open-low), open] = [2*open-... ] reflected; here
    we use [low, open] as the involvement zone; distribution = the high.
    Bearish is the mirror.
    """
    bullish = close >= open_
    if bullish:
        manip = low
        acc_bottom = low
        acc_top = open_
        dist = high
        shape = CandleShape.OLHC
    else:
        manip = high
        acc_top = high
        acc_bottom = open_
        dist = low
        shape = CandleShape.OHLC

    return PowerOfThree(
        shape=shape, open=open_, high=high, low=low, close=close,
        manipulation_extreme=manip,
        accumulation_top=acc_top, accumulation_bottom=acc_bottom,
        distribution_target=dist,
    )


def decompose_session(df: pd.DataFrame, start: int, end: int) -> PowerOfThree:
    """Aggregate bars ``[start, end]`` into one candle and decompose it (ep 18).

    Use this to read a London/NY session, a day, or a week as a single power-of-3
    candle (the open of the first bar, the high/low of the range, the close of
    the last bar).
    """
    seg = df.iloc[start:end + 1]
    return decompose(
        open_=float(seg["open"].iloc[0]),
        high=float(seg["high"].max()),
        low=float(seg["low"].min()),
        close=float(seg["close"].iloc[-1]),
    )

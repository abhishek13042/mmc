"""Previous-candle-high / previous-candle-low (PCH / PCL) and the candle-science
sweep (transcript 08, ~10:18 onward).

A swing point on one timeframe becomes a **previous candle high / low** when you
zoom out one timeframe: "what is a swing high on a different timeframe? ... that
swing high turns into a previous candle high" (transcript 08). So PCH/PCL are the
candle-science (lower-timeframe order-flow) lens on the same liquidity.

* :func:`previous_candle_high` / :func:`previous_candle_low` return the prior
  bar's high / low for a given bar — the level that the current bar can sweep.
* A **candle-science sweep** (transcript 08, ~18:50): price retraces into a PD
  array (FVG / FVA) and **the first candle does not reject**. Because the first
  candle fails to respect the array, the *next* candle sweeps the previous candle
  high/low (the wick beyond it) and price continues in the array's direction.
  On the lower timeframe that PCH/PCL is itself a swing high/low, so this is the
  same shape as an order-flow sweep seen one timeframe down (everything is
  fractal).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from mmc.core import Direction, FairValueGap, SwingType


def previous_candle_high(df: pd.DataFrame, index: int) -> Optional[float]:
    """High of the candle immediately before ``index`` (the PCH for that bar).

    Returns ``None`` for the first bar, which has no previous candle.
    """
    if index <= 0 or index >= len(df):
        return None
    return float(df["high"].to_numpy()[index - 1])


def previous_candle_low(df: pd.DataFrame, index: int) -> Optional[float]:
    """Low of the candle immediately before ``index`` (the PCL for that bar)."""
    if index <= 0 or index >= len(df):
        return None
    return float(df["low"].to_numpy()[index - 1])


@dataclass
class CandleScienceSweep:
    """A PCH/PCL sweep where the first candle into the array does not reject.

    ``direction``    polarity we continue in (the array's direction): a discount
                     (bullish) array sweeps a previous candle *low*; a premium
                     (bearish) array sweeps a previous candle *high*.
    ``level``        the previous candle high/low that was swept.
    ``level_index``  index of the candle whose high/low is ``level`` (the
                     non-rejecting first candle).
    ``sweep_index``  index of the candle that swept ``level`` (the next candle's
                     wick beyond it).
    ``array``        the FVG/FVA being retraced into (an FVG here).
    """

    direction: Direction
    level: float
    level_index: int
    sweep_index: int
    array: Optional[FairValueGap] = None

    @property
    def kind(self) -> SwingType:
        """The swept PCH/PCL is a swing high (premium) or swing low (discount)
        on the lower timeframe."""
        return SwingType.LOW if self.direction is Direction.BULLISH else SwingType.HIGH


def candle_science_sweeps(
    df: pd.DataFrame,
    fvgs: List[FairValueGap],
) -> List[CandleScienceSweep]:
    """Detect candle-science (PCH/PCL) sweeps off the given FVGs.

    For each FVG we look at the first bar that retraces into the array. If that
    first candle **does not reject** (does not close back out of the array in the
    array's favour) and the *next* candle wicks beyond that first candle's
    PCL (bullish array) / PCH (bearish array) but closes back in the array's
    direction, we record a candle-science sweep.

    Note (transcript 08): an FVG can be traded into only once; an already
    mitigated FVG is dropped — what is swept is the previous candle low/high
    (a swing point on the lower timeframe) left behind, not the FVG itself.
    """
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    low = df["low"].to_numpy()
    c = df["close"].to_numpy()
    n = len(df)
    out: List[CandleScienceSweep] = []

    for f in fvgs:
        # First bar after confirmation that trades into the gap.
        first = None
        for j in range(f.c3_index + 1, n):
            if f.direction is Direction.BULLISH and low[j] <= f.top:
                first = j
                break
            if f.direction is Direction.BEARISH and h[j] >= f.bottom:
                first = j
                break
        if first is None or first + 1 >= n:
            continue

        nxt = first + 1
        if f.direction is Direction.BULLISH:
            # First candle does not reject = it is bearish (no respect up).
            first_rejects = c[first] > o[first]
            pcl = low[first]
            swept = low[nxt] < pcl and c[nxt] > o[nxt]  # wick below, close up
            if not first_rejects and swept:
                out.append(
                    CandleScienceSweep(
                        direction=Direction.BULLISH,
                        level=float(pcl),
                        level_index=first,
                        sweep_index=nxt,
                        array=f,
                    )
                )
        else:  # bearish array
            first_rejects = c[first] < o[first]
            pch = h[first]
            swept = h[nxt] > pch and c[nxt] < o[nxt]  # wick above, close down
            if not first_rejects and swept:
                out.append(
                    CandleScienceSweep(
                        direction=Direction.BEARISH,
                        level=float(pch),
                        level_index=first,
                        sweep_index=nxt,
                        array=f,
                    )
                )

    return out

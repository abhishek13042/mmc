"""Fair Value Gap quality classification (transcript 06 — Fair Value Gaps).

Not every FVG is equal. An FVG is a 3-candle pattern; candle 2 (the
*expansion-phase* candle) defines the **potential** gap and candle 3 determines
the **type**:

* **Rejection FVG** ("rejection") — a large opposing 3rd candle eats most of the
  potential gap, leaving only a small *realized* gap. Too much opposing strength
  -> the **worst** FVG to trade from.
* **Perfect FVG** ("perfect") — a consolidation 3rd candle: enough opposing
  strength for a retracement (a real gap remains) but not a full rejection. The
  ~80/20 balance -> the **best** FVG to trade from.
* **Breakaway gap** ("breakaway") — an expansion 3rd candle: ~one-sided strength,
  almost no opposing wick, price keeps going. Not worst / not best.

Modelling (geometry from the transcript):

The *potential gap* is how big the gap could have been once candle 2 closed
beyond candle 1 (transcript: "this whole gray box is where we can potentially
see a fair value gap"). For a bullish FVG candle 2 closes above candle 1's high,
so the potential gap spans ``candle1.high -> candle2.close``. The *realized gap*
is what actually remained (``FairValueGap.size`` == ``c3.low - c1.high``).

``fill = 1 - realized/potential`` is the fraction of the potential gap eaten by
candle 3's opposing move:

* high ``fill`` (small realized gap, big opposing 3rd candle) -> **rejection**.
* the 3rd candle expanding *with* the gap (its close pushing further than its
  predecessor, little opposing wick) -> **breakaway**.
* otherwise a real gap remains with a modest opposing retracement -> **perfect**.
"""

from __future__ import annotations

from typing import List

import pandas as pd

from mmc.core import Direction, FairValueGap

# Fraction of the potential gap that must be eaten by candle 3 for a rejection.
REJECTION_FILL = 0.75
# Opposing wick (relative to the c3 body) above which a one-sided c3 is *not*
# treated as a clean breakaway expansion.
BREAKAWAY_MAX_OPPOSING_WICK = 0.5


def _potential_gap(df: pd.DataFrame, fvg: FairValueGap) -> float:
    """Size of the gap candle 2's close *could* have left open.

    Bullish: ``candle2.close - candle1.high``. Bearish: ``candle1.low -
    candle2.close``. This is the "gray box" of potential fair value (transcript
    06) before candle 3 trades back through part of it.
    """
    c1 = df.iloc[fvg.c1_index]
    c2 = df.iloc[fvg.c2_index]
    if fvg.direction is Direction.BULLISH:
        return float(c2["close"]) - float(c1["high"])
    return float(c1["low"]) - float(c2["close"])


def classify_fvg(df: pd.DataFrame, fvg: FairValueGap) -> str:
    """Set and return ``fvg.quality`` -> "rejection" | "perfect" | "breakaway".

    Uses candle-3 geometry per transcript 06: how much of the potential gap was
    eaten (rejection) versus the 3rd candle expanding one-sided (breakaway), with
    the balanced middle ground being the perfect FVG.
    """
    potential = _potential_gap(df, fvg)
    realized = fvg.size

    # Degenerate / zero-potential gap: fall back to perfect (a clean gap exists).
    if potential <= 0:
        fvg.quality = "perfect"
        return fvg.quality

    fill = 1.0 - (realized / potential)  # fraction of potential gap eaten by c3
    fill = max(0.0, min(1.0, fill))

    c2 = df.iloc[fvg.c2_index]
    c3 = df.iloc[fvg.c3_index]
    o3, h3, l3, cl3 = (
        float(c3["open"]),
        float(c3["high"]),
        float(c3["low"]),
        float(c3["close"]),
    )
    body3 = abs(cl3 - o3)
    range3 = h3 - l3

    if fvg.direction is Direction.BULLISH:
        # A bullish 3rd candle expanding the move closes above candle 2's close
        # with little opposing (lower-side) wick.
        c3_expands = cl3 >= float(c2["close"])
        opposing_wick = min(o3, cl3) - l3  # lower wick == bearish/opposing
    else:
        c3_expands = cl3 <= float(c2["close"])
        opposing_wick = h3 - max(o3, cl3)  # upper wick == bullish/opposing

    small_opposing_wick = body3 > 0 and opposing_wick <= BREAKAWAY_MAX_OPPOSING_WICK * body3

    if fill >= REJECTION_FILL:
        # Most of the potential gap eaten by a large opposing 3rd candle.
        fvg.quality = "rejection"
    elif c3_expands and small_opposing_wick and range3 > 0:
        # One-sided expansion 3rd candle continuing the move, no retracement.
        fvg.quality = "breakaway"
    else:
        # A real gap remains with only a modest opposing retracement.
        fvg.quality = "perfect"
    return fvg.quality


def classify_fvgs(df: pd.DataFrame, fvgs: List[FairValueGap]) -> List[FairValueGap]:
    """Classify every FVG in-place and return the same list for chaining."""
    for fvg in fvgs:
        classify_fvg(df, fvg)
    return fvgs

"""Market structure, fair value areas and order flow lags
(transcripts 02 & 03 — the rest of the foundation).

Definitions (from the transcripts):

* **Intermediate-Term High (ITH)** — a swing high with a *lower* swing high to
  its left and right. ITL is the mirror.
* **Short-Term High (STH)** — a swing high *followed by an FVG* (it does not need
  lower swing highs either side). STL is the mirror.
* **Fair Value Area (FVA)** — the zone left by a three-swing movement, spanning
  from an intermediate/short-term high to the opposing low.
* **Order Flow Lag** — a swing point **plus** an FVG (plus the FVA it leaves).
  No FVG => no order flow lag.

The narrative layer (transcript 04) later classifies each lag's FLOD/ODD/LOD and
the quality of its FVG/FVA; this module only assembles the raw structures.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

from .fvg import find_fvgs
from .swings import find_swings, swing_highs, swing_lows
from .types import (
    Direction,
    FairValueArea,
    FairValueGap,
    OrderFlowLag,
    StructurePoint,
    StructurePointType,
    SwingPoint,
    SwingType,
)

# --------------------------------------------------------------------------- #
# Intermediate-term structure (transcript 02)
# --------------------------------------------------------------------------- #


def intermediate_term_points(swings: List[SwingPoint]) -> List[StructurePoint]:
    """Return ITH/ITL structure points derived from a swing list.

    ITH: swing high with a lower swing high immediately before and after it
    (among swing highs). ITL: swing low with a higher swing low either side.
    """
    highs = swing_highs(swings)
    lows = swing_lows(swings)
    points: List[StructurePoint] = []

    for j in range(1, len(highs) - 1):
        if highs[j].price > highs[j - 1].price and highs[j].price > highs[j + 1].price:
            points.append(StructurePoint(swing=highs[j], kind=StructurePointType.ITH))

    for j in range(1, len(lows) - 1):
        if lows[j].price < lows[j - 1].price and lows[j].price < lows[j + 1].price:
            points.append(StructurePoint(swing=lows[j], kind=StructurePointType.ITL))

    points.sort(key=lambda p: p.index)
    return points


# --------------------------------------------------------------------------- #
# Short-term structure (transcript 03) — swing + FVG
# --------------------------------------------------------------------------- #


def short_term_points(
    swings: List[SwingPoint],
    fvgs: List[FairValueGap],
    window: int = 3,
) -> List[StructurePoint]:
    """Return STH/STL structure points: a swing immediately followed by an FVG.

    A swing high becomes an STH if a *bearish* FVG forms within ``window`` bars
    after the swing; a swing low becomes an STL with a following *bullish* FVG.
    """
    points: List[StructurePoint] = []

    for s in swings:
        wanted = Direction.BEARISH if s.kind is SwingType.HIGH else Direction.BULLISH
        match: Optional[FairValueGap] = None
        for f in fvgs:
            if f.direction is not wanted:
                continue
            if s.index <= f.c1_index <= s.index + window:
                match = f
                break
        if match is not None:
            kind = (
                StructurePointType.STH
                if s.kind is SwingType.HIGH
                else StructurePointType.STL
            )
            points.append(StructurePoint(swing=s, kind=kind, fvg=match))

    points.sort(key=lambda p: p.index)
    return points


# --------------------------------------------------------------------------- #
# Fair Value Areas (transcript 02 / 07)
# --------------------------------------------------------------------------- #


def fair_value_areas(points: List[StructurePoint]) -> List[FairValueArea]:
    """Pair consecutive opposing structure points into FVAs (three-swing moves).

    A high followed by a low produces a bearish (premium) FVA spanning their
    prices; a low followed by a high produces a bullish (discount) FVA.
    """
    areas: List[FairValueArea] = []
    ordered = sorted(points, key=lambda p: p.index)

    for a, b in zip(ordered, ordered[1:]):
        if a.is_high == b.is_high:
            continue  # need an opposing pair (high then low, or low then high)
        direction = Direction.BEARISH if a.is_high else Direction.BULLISH
        hi = a if a.is_high else b
        lo = b if a.is_high else a
        areas.append(
            FairValueArea(
                top=hi.price,
                bottom=lo.price,
                index=b.index,
                direction=direction,
                start=a,
                end=b,
            )
        )
    return areas


# --------------------------------------------------------------------------- #
# Order flow lags (transcript 03) — the central object
# --------------------------------------------------------------------------- #


def find_order_flow_lags(
    swings: List[SwingPoint],
    fvgs: List[FairValueGap],
    window: int = 3,
) -> List[OrderFlowLag]:
    """Assemble order flow lags: each FVG paired with the nearest preceding swing
    of matching polarity (swing high for a bearish FVG, swing low for a bullish
    FVG) whose FVG forms within ``window`` bars.

    FLOD/ODD/LOD classification and FVA attachment are left to the narrative
    layer; this returns the raw ``swing + fvg`` lags.
    """
    highs = swing_highs(swings)
    lows = swing_lows(swings)
    lags: List[OrderFlowLag] = []

    for f in fvgs:
        if f.direction is Direction.BEARISH:
            candidates = [s for s in highs if s.index <= f.c1_index]
        else:
            candidates = [s for s in lows if s.index <= f.c1_index]
        if not candidates:
            continue
        swing = max(candidates, key=lambda s: s.index)  # nearest preceding
        if f.c1_index - swing.index > window:
            continue
        lags.append(
            OrderFlowLag(direction=f.direction, swing=swing, fvg=f, lod=swing)
        )

    lags.sort(key=lambda lg: lg.index)
    return lags


# --------------------------------------------------------------------------- #
# Convenience: full structural pass over a DataFrame
# --------------------------------------------------------------------------- #


def analyze(df: pd.DataFrame, window: int = 3) -> dict:
    """Run the full foundation pass and return every structural object.

    Returns a dict with keys: ``swings``, ``fvgs``, ``intermediate``,
    ``short_term``, ``fvas``, ``order_flow_lags``.
    """
    swings = find_swings(df)
    fvgs = find_fvgs(df)
    intermediate = intermediate_term_points(swings)
    return {
        "swings": swings,
        "fvgs": fvgs,
        "intermediate": intermediate,
        "short_term": short_term_points(swings, fvgs, window=window),
        "fvas": fair_value_areas(intermediate),
        "order_flow_lags": find_order_flow_lags(swings, fvgs, window=window),
    }

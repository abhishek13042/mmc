"""Unusual context detection (transcript 10, ~13:56 onward).

The market is doing one of two things: **offering fair value** or **seeking
liquidity**. When an FVA's rejection *fails* and price creates an opposing FVG
instead, the FVA is no longer offering fair value — it is seeking liquidity, and
the target becomes the FVA's **far side** (transcript 10, ~14:42 / ~15:04).

This is the *bigger picture* unusual context; the FVG we then trade is itself a
**usual** context area, with the FVA far side as its external target. We always
trade usual context, even inside unusual context (transcript 10, ~15:51).

We reuse:
* ``mmc.narrative.is_seeking_liquidity`` — detects the deep retracement past the
  FVA (rejection failed).
* FVA quality ``"swept"`` (``mmc.narrative.classify_fva``) — the FVA stopped
  offering fair value (no overlapping FVG / already being swept).
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

from mmc.core import (
    Direction,
    FairValueArea,
    FairValueGap,
    SwingPoint,
    Zone,
    fair_value_areas,
    find_fvgs,
    find_order_flow_lags,
    find_swings,
    intermediate_term_points,
    mark_mitigation,
)
from mmc.narrative import classify_fva, decompose_lag, is_seeking_liquidity

from .area import ContextArea
from .targets import first_opposing_pd_array


def _fva_far_side(fva: FairValueArea) -> SwingPoint:
    """The FVA's far side as a target: the **low** for a bullish (discount) lag
    being abandoned downward, the **high** for a bearish one (transcript 10,
    ~14:42 — the FVA low/high becomes the liquidity target)."""
    if fva.direction is Direction.BULLISH:
        # bullish FVA: seeking liquidity DOWN -> target the FVA low
        return SwingPoint(index=fva.index, price=fva.bottom, kind=_far_kind(fva))
    return SwingPoint(index=fva.index, price=fva.top, kind=_far_kind(fva))


def _far_kind(fva: FairValueArea):
    from mmc.core import SwingType

    return SwingType.LOW if fva.direction is Direction.BULLISH else SwingType.HIGH


def _opposing_fvg_after(
    fva: FairValueArea, fvgs: List[FairValueGap]
) -> Optional[FairValueGap]:
    """The first FVG of polarity *opposite* the FVA that confirms after it.

    When a bullish FVA fails to offer fair value, an opposing **bearish** FVG
    forms and that FVG is the usual context to trade towards the FVA low
    (transcript 10, ~14:49). We require its band to sit within the FVA so it is
    the deep-retracement FVG, not an unrelated gap.
    """
    opposing = fva.direction.opposite
    matches = [
        f
        for f in fvgs
        if f.direction is opposing
        and f.c1_index >= fva.index
        and f.bottom <= fva.top
        and f.top >= fva.bottom
    ]
    if not matches:
        return None
    return min(matches, key=lambda f: f.c3_index)


def find_unusual_context(
    df: pd.DataFrame,
    swings: Optional[List[SwingPoint]] = None,
    fvgs: Optional[List[FairValueGap]] = None,
    fvas: Optional[List[FairValueArea]] = None,
    window: int = 3,
) -> List[ContextArea]:
    """Return unusual-context areas: an FVA that stopped offering fair value, and
    the usual-context opposing FVG that trades towards its far side.

    For each order flow lag whose FVA is **seeking liquidity** (a failed
    rejection / deep retracement past the FVA) we find the opposing FVG that
    formed inside the FVA. That FVG is the boundary of a *usual* context area;
    its target is the first opposing PD array; its ``external_target`` is the
    FVA's far side (the liquidity). ``kind`` is "unusual" to flag the bigger
    picture.
    """
    if swings is None:
        swings = find_swings(df)
    if fvgs is None:
        fvgs = find_fvgs(df)
        mark_mitigation(df, fvgs)
    if fvas is None:
        fvas = fair_value_areas(intermediate_term_points(swings))

    out: List[ContextArea] = []
    lags = find_order_flow_lags(swings, fvgs, window=window)
    seen_fvg_indices: set[int] = set()

    for lag in lags:
        decompose_lag(lag, df=df, fvas=fvas)
        fva = lag.fva
        if fva is None:
            continue
        if not is_seeking_liquidity(lag, df):
            continue
        # The FVA stopped offering fair value: quality "swept" (no overlapping
        # FVG / already being swept) confirms the unusual-context setup.
        classify_fva(fva, fvgs, fvas=fvas, df=df)

        opp_fvg = _opposing_fvg_after(fva, fvgs)
        if opp_fvg is None or opp_fvg.c3_index in seen_fvg_indices:
            continue
        seen_fvg_indices.add(opp_fvg.c3_index)

        # The opposing FVG is the *usual* context we trade; its direction is the
        # FVG's polarity (opposite the FVA). Target = first opposing PD array;
        # external target = the FVA's far side (the liquidity being sought).
        target = first_opposing_pd_array(
            opp_fvg.direction, opp_fvg.index, df, swings, fvgs
        )
        if target is None:
            target = _fva_far_side(fva)
        out.append(
            ContextArea(
                boundary=opp_fvg,
                target=target,
                direction=opp_fvg.direction,
                kind="unusual",
                defense="LOD",  # the FVA's far side (LOD) is what we trade towards
                external_target=_fva_far_side(fva),
            )
        )

    out.sort(key=lambda a: a.boundary.index)
    return out

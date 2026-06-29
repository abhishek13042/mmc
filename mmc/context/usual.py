"""Usual context detection (transcript 10).

We always trade **usual context** (transcript 10, ~1:02). From the order flow
lags (``mmc.core.find_order_flow_lags`` + ``mmc.narrative.decompose_lag``) we
build one context area per defense:

* **FLOD context** — the **FVG** is the boundary; target = first opposing swing
  (else previous candle high/low). High-probability lags (FVG is the FLOD).
* **ODD context** — the **FVA** is the boundary; target = first opposing PD
  array.
* **LOD context** — two forms (transcript 10, ~9:56):
    (a) a **swing low/high** (a lag with *no FVG*) is the boundary; target = the
        opposing swing — the swing is the only thing to trade from / sweep.
    (b) a **previous-candle-low/high sweep** is the boundary (candle-science
        sweep, ``mmc.sweeps.candle_science_sweeps``); target = first opposing PD
        array.

The boundary is always the array a retracement hits *first* in the lag, which is
exactly what ``decompose_lag`` puts in ``lag.flod`` — so FLOD/ODD context follow
directly from the narrative decomposition.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

from mmc.core import (
    Direction,
    FairValueArea,
    FairValueGap,
    SwingPoint,
    SwingType,
    Zone,
    find_fvgs,
    find_order_flow_lags,
    find_swings,
    mark_mitigation,
)
from mmc.narrative import decompose_lag
from mmc.sweeps import candle_science_sweeps

from .area import ContextArea
from .targets import first_opposing_pd_array


def _swing_zone(swing: SwingPoint) -> Zone:
    """A degenerate (zero-height) zone at a swing's price — a boundary you enter
    on as price returns to the swing level (transcript 10 LOD form (a))."""
    return Zone(
        top=swing.price,
        bottom=swing.price,
        index=swing.index,
        direction=swing.direction,
    )


def _level_zone(level: float, index: int, direction: Direction) -> Zone:
    """A degenerate zone at a previous-candle high/low level (LOD form (b))."""
    return Zone(top=level, bottom=level, index=index, direction=direction)


def find_context_areas(
    df: pd.DataFrame,
    swings: Optional[List[SwingPoint]] = None,
    fvgs: Optional[List[FairValueGap]] = None,
    fvas: Optional[List[FairValueArea]] = None,
    window: int = 3,
) -> List[ContextArea]:
    """Return all usual context areas in ``df`` (FLOD / ODD / LOD).

    Pure function over the DataFrame: detects swings/FVGs/lags via the core
    layer if not supplied, decomposes each lag via the narrative layer, then
    emits the FLOD and ODD context areas. LOD context areas (swing-only lags and
    candle-science sweeps) are added on top.
    """
    if swings is None:
        swings = find_swings(df)
    if fvgs is None:
        fvgs = find_fvgs(df)
        mark_mitigation(df, fvgs)

    areas: List[ContextArea] = []

    lags = find_order_flow_lags(swings, fvgs, window=window)
    for lag in lags:
        decompose_lag(lag, df=df, fvas=fvas)
        boundary = lag.flod  # the array a retrace hits first = the boundary
        if boundary is None:
            continue
        target = first_opposing_pd_array(
            lag.direction, boundary.index, df, swings, fvgs
        )
        if target is None:
            continue
        # FLOD context if the boundary is the FVG; ODD context if it's the FVA.
        if isinstance(boundary, FairValueArea):
            defense = "ODD"
        else:
            defense = "FLOD"
        areas.append(
            ContextArea(
                boundary=boundary,
                target=target,
                direction=lag.direction,
                kind="usual",
                defense=defense,
            )
        )

    areas.extend(_lod_swing_contexts(df, swings, fvgs, window=window))
    areas.extend(_lod_candle_science_contexts(df, swings, fvgs))

    areas.sort(key=lambda a: a.boundary.index)
    return areas


def _lod_swing_contexts(
    df: pd.DataFrame,
    swings: List[SwingPoint],
    fvgs: List[FairValueGap],
    window: int,
) -> List[ContextArea]:
    """LOD form (a): a swing with *no* FVG in its lag is the boundary.

    A swing that does not produce an order flow lag (no FVG follows it) is the
    only thing left to trade from / sweep (transcript 10, ~10:10). The boundary
    is the swing; the target is the opposing swing.
    """
    lag_swing_indices = {
        lag.swing.index for lag in find_order_flow_lags(swings, fvgs, window=window)
    }
    out: List[ContextArea] = []
    for s in swings:
        if s.index in lag_swing_indices:
            continue  # this swing already drives an FVG lag (FLOD/ODD covers it)
        direction = s.direction  # a swing low continues bullish; a high bearish
        target = first_opposing_pd_array(direction, s.index, df, swings, fvgs)
        if target is None:
            continue
        out.append(
            ContextArea(
                boundary=_swing_zone(s),
                target=target,
                direction=direction,
                kind="usual",
                defense="LOD",
            )
        )
    return out


def _lod_candle_science_contexts(
    df: pd.DataFrame,
    swings: List[SwingPoint],
    fvgs: List[FairValueGap],
) -> List[ContextArea]:
    """LOD form (b): a previous-candle-low/high sweep is the boundary.

    Uses the sweeps layer's candle-science sweeps (transcript 08 / 10, ~10:39):
    the first candle into an FVG does not reject, the next candle sweeps the
    previous candle low/high, and price continues towards the first opposing PD
    array. The swept previous candle level is the boundary.
    """
    out: List[ContextArea] = []
    for sweep in candle_science_sweeps(df, fvgs):
        boundary = _level_zone(sweep.level, sweep.level_index, sweep.direction)
        target = first_opposing_pd_array(
            sweep.direction, sweep.sweep_index, df, swings, fvgs
        )
        if target is None:
            continue
        out.append(
            ContextArea(
                boundary=boundary,
                target=target,
                direction=sweep.direction,
                kind="usual",
                defense="LOD",
            )
        )
    return out

"""The mechanical context *target* rule (transcript 10).

The target of a context area is the **first opposing PD array**: if we expect
higher from a discount array the target is the nearest premium array (a swing
high); if there is no swing the target is the **previous candle high** (and the
mirror for a bearish move) — transcript 10, ~4:53 / ~5:14.

We reuse :func:`mmc.narrative.opposing_pd_arrays` for the swing/FVG candidates
(never re-deriving them) and the sweeps-layer PCH/PCL helpers for the
previous-candle fallback.
"""

from __future__ import annotations

from typing import List, Optional, Union

import pandas as pd

from mmc.core import (
    Direction,
    FairValueGap,
    SwingPoint,
    SwingType,
    Zone,
)
from mmc.narrative import opposing_pd_arrays
from mmc.sweeps import previous_candle_high, previous_candle_low

Target = Union[SwingPoint, Zone]


def _prev_candle_target(
    direction: Direction, from_index: int, df: pd.DataFrame
) -> Optional[SwingPoint]:
    """Fallback target: the previous candle high/low as a swing-shaped target.

    For a bullish move the opposing (premium) level is the previous candle
    *high*; for a bearish move it is the previous candle *low* (transcript 10,
    ~5:00). We wrap it as a :class:`SwingPoint` so callers get a uniform target
    type with a ``price``.
    """
    if direction is Direction.BULLISH:
        level = previous_candle_high(df, from_index)
        kind = SwingType.HIGH
    else:
        level = previous_candle_low(df, from_index)
        kind = SwingType.LOW
    if level is None:
        return None
    return SwingPoint(index=from_index - 1, price=float(level), kind=kind)


def first_opposing_pd_array(
    direction: Direction,
    from_index: int,
    df: pd.DataFrame,
    swings: List[SwingPoint],
    fvgs: List[FairValueGap],
) -> Optional[Target]:
    """Return the nearest opposing PD array *after* ``from_index`` (the target).

    Preference order (transcript 10):

    1. The first unmitigated opposing **swing point** (a swing high for a bullish
       move, a swing low for a bearish move) that confirms after ``from_index``.
    2. Otherwise the first opposing **FVG** after ``from_index`` (still an
       objective PD array).
    3. Otherwise the **previous candle high/low** at ``from_index`` (the
       candle-science fallback).

    ``from_index`` is the boundary's confirming index; the target must lie ahead
    of it. Returns ``None`` only when there is no candle to fall back on.
    """
    candidates = opposing_pd_arrays(direction, swings, fvgs)
    ahead = [a for a in candidates if a.index > from_index]

    # Prefer an actual swing point (transcript 10 — "ideally a swing high").
    swing_targets = [a for a in ahead if isinstance(a, SwingPoint)]
    if swing_targets:
        return min(swing_targets, key=lambda a: a.index)

    # Else the nearest opposing FVG.
    if ahead:
        return min(ahead, key=lambda a: a.index)

    # Else fall back to the previous candle high/low (candle science).
    return _prev_candle_target(direction, from_index, df)

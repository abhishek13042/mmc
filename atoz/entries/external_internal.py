"""External / Internal moves + Market Structure Shift (A-Z Guide ep 11, also ep 10).

> An **external** move is a sweep of liquidity (a turtle soup — price trades
> beyond a swing). An **internal** move respects FVGs / blocks (rebalancing).
> The tell for which comes next: an **FVG in the leg** → the move is internal
> (the swing is *less* likely to be swept again). A **Market Structure Shift
> (MSS)** is when, after an external sweep, price breaks the opposing swing
> (a wick is enough — no close needed). The sequence to trade is
> external → internal → (new internal) = entry.  — ep 11
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pandas as pd

from atoz.core.fvg import FVG, find_fvgs
from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Candles, Direction, Swing, SwingType


class MoveType(Enum):
    EXTERNAL = "external"   # sweep of liquidity (turtle soup)
    INTERNAL = "internal"   # FVG/block respected (rebalancing)


@dataclass
class MarketStructureShift:
    """An external sweep followed by a break of the opposing swing (ep 11)."""

    direction: Direction        # the *new* direction after the shift
    sweep_index: int            # where liquidity was swept (external)
    shift_index: int            # where the opposing swing broke (MSS)
    swept_swing: Swing
    broken_swing: Swing
    has_fvg_in_leg: bool        # FVG in the impulse leg → higher-prob internal


def classify_move(
    df: pd.DataFrame,
    from_index: int,
    to_index: int,
    fvgs: Optional[List[FVG]] = None,
) -> MoveType:
    """A leg with an FVG inside it is INTERNAL (rebalancing); otherwise the move
    that took out a swing is EXTERNAL (a liquidity sweep) — ep 11.

    The FVG is considered "in the leg" if any part of its 3-candle span
    (c1_index to c3_index) overlaps with the leg range [from_index, to_index].
    Using only the middle-candle index would miss FVGs that straddle the
    leg boundaries.
    """
    if fvgs is None:
        fvgs = find_fvgs(df)
    lo, hi = min(from_index, to_index), max(from_index, to_index)
    has_fvg = any(f.c1_index <= hi and f.c3_index >= lo for f in fvgs)
    return MoveType.INTERNAL if has_fvg else MoveType.EXTERNAL


def find_market_structure_shifts(
    df: pd.DataFrame,
    swings: Optional[List[Swing]] = None,
) -> List[MarketStructureShift]:
    """Detect external→MSS events: a swing is swept, then the opposing swing is
    broken (the shift). The new direction is toward the broken swing (ep 11).
    """
    c = Candles.of(df)
    if swings is None:
        swings = find_swings(df)
    fvgs = find_fvgs(df)
    ordered = sorted(swings, key=lambda s: s.index)

    out: List[MarketStructureShift] = []
    for i, swept in enumerate(ordered):
        # find where this swing is swept (external)
        sweep_at = None
        for k in range(swept.index + 1, c.n):
            if swept.kind is SwingType.LOW and c.low[k] < swept.price:
                sweep_at = k
                break
            if swept.kind is SwingType.HIGH and c.high[k] > swept.price:
                sweep_at = k
                break
        if sweep_at is None:
            continue

        # the opposing swing to break for the shift (a low swept → break a high)
        want = SwingType.HIGH if swept.kind is SwingType.LOW else SwingType.LOW
        opposing = next(
            (s for s in ordered if s.index > swept.index and s.index < sweep_at and s.kind is want),
            None,
        )
        if opposing is None:
            continue

        shift_at = None
        for k in range(sweep_at, min(c.n, sweep_at + 50)):
            if want is SwingType.HIGH and c.high[k] > opposing.price:
                shift_at = k
                break
            if want is SwingType.LOW and c.low[k] < opposing.price:
                shift_at = k
                break
        if shift_at is None:
            continue

        new_dir = Direction.BULLISH if swept.kind is SwingType.LOW else Direction.BEARISH
        has_fvg = any(sweep_at <= f.index <= shift_at and f.direction is new_dir for f in fvgs)
        out.append(
            MarketStructureShift(
                direction=new_dir, sweep_index=sweep_at, shift_index=shift_at,
                swept_swing=swept, broken_swing=opposing, has_fvg_in_leg=has_fvg,
            )
        )
    return out

"""Imbalances (A-Z Guide ep 8): FVG / BISI-SIBI / BPR / Liquidity Void /
Volume Imbalance.

> A **fair value gap** is a 3-candle imbalance (a body between two non-
> overlapping wicks). **BISI** = buy-side imbalance / sell-side inefficiency =
> a *bullish* FVG; **SIBI** = the bearish FVG. A **BPR** (balanced price range)
> is an overlapping BISI + SIBI — you take only the overlap. A **liquidity
> void** is a gap with *no* delivery on either side (a true price gap, e.g.
> news / session open) — an even stronger magnet than an FVG. A **volume
> imbalance** is a 2-candle gap between the *bodies* (close→open) while the
> wicks may still touch.  — ep 8

FVG/BISI/SIBI live in :mod:`atoz.core.fvg`. This module adds BPR, liquidity
voids and volume imbalances, plus BISI/SIBI naming helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pandas as pd

from atoz.core.fvg import FVG, find_fvgs
from atoz.core.types import Candles, Direction, Zone


class ImbalanceType(Enum):
    BPR = "balanced_price_range"
    LIQUIDITY_VOID = "liquidity_void"
    VOLUME_IMBALANCE = "volume_imbalance"


@dataclass
class Imbalance(Zone):
    kind: ImbalanceType = ImbalanceType.BPR


def label_bisi_sibi(fvg: FVG) -> str:
    """BISI (bullish FVG) / SIBI (bearish FVG) — the ep-8 naming."""
    return "BISI" if fvg.direction is Direction.BULLISH else "SIBI"


def find_bpr(df: pd.DataFrame, fvgs: Optional[List[FVG]] = None) -> List[Imbalance]:
    """Balanced Price Range: a bullish FVG overlapping a bearish FVG. The zone is
    only the *overlap* of the two gaps (ep 8)."""
    if fvgs is None:
        fvgs = find_fvgs(df)
    bull = [f for f in fvgs if f.direction is Direction.BULLISH]
    bear = [f for f in fvgs if f.direction is Direction.BEARISH]

    out: List[Imbalance] = []
    for b in bull:
        for s in bear:
            top = min(b.top, s.top)
            bottom = max(b.bottom, s.bottom)
            if top > bottom:  # they overlap
                # polarity = the later gap's polarity (the active intent)
                direction = b.direction if b.index > s.index else s.direction
                out.append(
                    Imbalance(top=top, bottom=bottom, index=max(b.index, s.index),
                              direction=direction, kind=ImbalanceType.BPR)
                )
    out.sort(key=lambda z: z.index)
    return out


def find_liquidity_voids(df: pd.DataFrame, min_atr_mult: float = 1.0) -> List[Imbalance]:
    """Liquidity void: consecutive candles whose *ranges* do not overlap — a true
    gap with no delivery either side (ep 8). Filtered to gaps ≥ ``min_atr_mult``
    ATR so only meaningful voids are kept."""
    c = Candles.of(df)
    atr = float((df["high"] - df["low"]).tail(14).mean()) or 1e-9
    out: List[Imbalance] = []
    for i in range(1, c.n):
        # bullish void: this low above previous high
        if c.low[i] > c.high[i - 1] and (c.low[i] - c.high[i - 1]) >= min_atr_mult * atr:
            out.append(Imbalance(top=float(c.low[i]), bottom=float(c.high[i - 1]),
                                 index=i, direction=Direction.BULLISH,
                                 kind=ImbalanceType.LIQUIDITY_VOID))
        # bearish void: this high below previous low
        elif c.high[i] < c.low[i - 1] and (c.low[i - 1] - c.high[i]) >= min_atr_mult * atr:
            out.append(Imbalance(top=float(c.low[i - 1]), bottom=float(c.high[i]),
                                 index=i, direction=Direction.BEARISH,
                                 kind=ImbalanceType.LIQUIDITY_VOID))
    return out


def find_volume_imbalances(df: pd.DataFrame) -> List[Imbalance]:
    """Volume imbalance: a 2-candle gap between the bodies (prev close → this
    open) while the candle ranges still overlap (ep 8).

    Per ep 8: "a volume imbalance is when there is a space between two candles
    ... there is a little bit of space between this close and this open of the
    candles."  The defining gap is the body gap (close → open), not the shadow.
    The ranges-overlap check distinguishes a VI from a full liquidity void.
    """
    c = Candles.of(df)
    out: List[Imbalance] = []
    for i in range(1, c.n):
        prev_close = c.close[i - 1]
        this_open = c.open[i]
        # ranges must overlap (otherwise it's a liquidity void, not a VI)
        ranges_touch = c.low[i] <= c.high[i - 1] and c.high[i] >= c.low[i - 1]
        if not ranges_touch:
            continue
        # Bullish VI: open gaps above previous close
        if this_open > prev_close:
            out.append(Imbalance(top=float(this_open), bottom=float(prev_close),
                                 index=i, direction=Direction.BULLISH,
                                 kind=ImbalanceType.VOLUME_IMBALANCE))
        # Bearish VI: open gaps below previous close
        elif this_open < prev_close:
            out.append(Imbalance(top=float(prev_close), bottom=float(this_open),
                                 index=i, direction=Direction.BEARISH,
                                 kind=ImbalanceType.VOLUME_IMBALANCE))
    return out

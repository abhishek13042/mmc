"""Liquidity Pools (A-Z Guide ep 7).

> Above highs sit buy-stops (breakout buyers + short stop-losses); below lows
> sit sell-stops. Equal highs / equal lows, trendline liquidity and
> consolidation extremes are **liquidity pools** — the market moves from one
> pool to the next. Take one side, then target the opposite — but only **after a
> reaction** (displacement away). A **sweep** takes a level and rejects (targets
> the opposite side); a **run** keeps going through it.  — ep 7

This module detects the pools (equal highs/lows, consolidation extremes) and
classifies a level's fate as SWEEP vs RUN with the required reaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pandas as pd

from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Candles, Direction, Swing, SwingType


class PoolType(Enum):
    EQUAL_HIGHS = "equal_highs"
    EQUAL_LOWS = "equal_lows"
    SINGLE_HIGH = "single_high"
    SINGLE_LOW = "single_low"


@dataclass
class LiquidityPool:
    """A resting-liquidity level. ``price`` is the level; ``members`` are the
    swing indices that form it (≥2 for equal highs/lows)."""

    price: float
    kind: PoolType
    direction: Direction       # BEARISH above highs (sell), BULLISH below lows
    index: int                 # last bar that defines the pool
    members: List[int]
    swept: bool = False        # True once price has traded through the pool


class LiquidityEvent(Enum):
    SWEEP = "sweep"   # took the level and rejected (target opposite side)
    RUN = "run"       # kept going through the level (continuation)
    NONE = "none"


def find_liquidity_pools(
    df: pd.DataFrame,
    swings: Optional[List[Swing]] = None,
    tolerance: float = 0.0005,
) -> List[LiquidityPool]:
    """Detect equal-high / equal-low pools (and lone swings as single pools).

    ``tolerance`` is the fractional price distance within which two swings count
    as "relatively equal" (ep 7 — *relatively* equal highs/lows).
    """
    if swings is None:
        swings = find_swings(df)
    highs = swing_highs(swings)
    lows = swing_lows(swings)

    pools: List[LiquidityPool] = []
    pools += _equal_levels(highs, PoolType.EQUAL_HIGHS, Direction.BEARISH, tolerance)
    pools += _equal_levels(lows, PoolType.EQUAL_LOWS, Direction.BULLISH, tolerance)

    grouped_idx = {i for p in pools for i in p.members}
    for s in highs:
        if s.index not in grouped_idx:
            pools.append(LiquidityPool(s.price, PoolType.SINGLE_HIGH, Direction.BEARISH, s.index, [s.index]))
    for s in lows:
        if s.index not in grouped_idx:
            pools.append(LiquidityPool(s.price, PoolType.SINGLE_LOW, Direction.BULLISH, s.index, [s.index]))

    pools.sort(key=lambda p: p.index)

    # Mark pools that have already been traded through (swept or run).
    _mark_swept(df, pools)
    return pools


def _mark_swept(df: pd.DataFrame, pools: List[LiquidityPool]) -> None:
    """Set ``swept=True`` on each pool once price trades through its level."""
    c = Candles.of(df)
    for pool in pools:
        above = pool.kind in (PoolType.EQUAL_HIGHS, PoolType.SINGLE_HIGH)
        for k in range(pool.index + 1, c.n):
            if above and c.high[k] > pool.price:
                pool.swept = True
                break
            if not above and c.low[k] < pool.price:
                pool.swept = True
                break


def _equal_levels(swings: List[Swing], kind: PoolType, direction: Direction, tol: float) -> List[LiquidityPool]:
    """Cluster swings whose prices are within ``tol`` of each other."""
    out: List[LiquidityPool] = []
    used = set()
    for i, a in enumerate(swings):
        if a.index in used:
            continue
        members = [a]
        for b in swings[i + 1:]:
            if abs(b.price - a.price) / max(a.price, 1e-9) <= tol:
                members.append(b)
        if len(members) >= 2:
            for m in members:
                used.add(m.index)
            price = sum(m.price for m in members) / len(members)
            out.append(LiquidityPool(price, kind, direction, members[-1].index, [m.index for m in members]))
    return out


def classify_pool(
    df: pd.DataFrame,
    pool: LiquidityPool,
    reaction_atr_mult: float = 1.0,
    window: int = 20,
) -> LiquidityEvent:
    """Classify a pool's fate as SWEEP (take + reject) or RUN (continuation).

    After the level is first taken, a *reaction* of at least ``reaction_atr_mult``
    ATR back through the level within ``window`` bars = SWEEP (ep 7 — "we need a
    reaction first"). Otherwise the level was run (price kept going).
    """
    c = Candles.of(df)
    above = pool.kind in (PoolType.EQUAL_HIGHS, PoolType.SINGLE_HIGH)

    take = None
    for k in range(pool.index + 1, c.n):
        if above and c.high[k] > pool.price:
            take = k
            break
        if not above and c.low[k] < pool.price:
            take = k
            break
    if take is None:
        return LiquidityEvent.NONE

    atr = float((df["high"] - df["low"]).tail(14).mean())
    need = reaction_atr_mult * atr

    for k in range(take, min(c.n, take + window)):
        if above and (pool.price - c.low[k]) >= need and c.close[k] < pool.price:
            return LiquidityEvent.SWEEP
        if not above and (c.high[k] - pool.price) >= need and c.close[k] > pool.price:
            return LiquidityEvent.SWEEP
    return LiquidityEvent.RUN

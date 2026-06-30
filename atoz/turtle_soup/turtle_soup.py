"""Full Trading Plans using Turtle Soups (A-Z Guide ep 28).

A **turtle soup** is a liquidity-sweep reversal: price runs (a *Judas*) past a
swing high/low (or equal highs/lows), **sweeps** that liquidity, then rejects
and reverses. Ep 28 gives two complete trading plans built on turtle soups.

Quoted step sequence (ep 28):

> "range, quadrants, judas, liquidity sweep, ST model, entry, close, target"

Plan A — **Seek-and-destroy** (ranging / 50%-equilibrium conditions):
  1. Determine the **range** we are stuck in (high→low).
  2. Draw **quadrants**: 0-0.25 = *discount-discount*, 0.25-0.5 = discount-
     premium, 0.5-0.75 = premium-discount, 0.75-1.0 = *premium-premium*
     (0.5 = equilibrium).
  3. Only get involved coming off **premium-premium** (sell) or
     **discount-discount** (buy), targeting **equilibrium**.
  4. On the LTF: a **Judas** that **sweeps liquidity** (a swing high/low), then
     an **ST model** (first displacement, then a second one) → enter on an
     overlapping PD-ray covering the intermediate-term high/low.
  5. **Close target** — a liquidity pool / FVG / equilibrium close to EQ. "you
     are not using a very large target" — get in, get out (a 1:2 is plenty).

Plan B — **Trending** turtle soups (two techniques):
  * Enter on the anticipated liquidity sweep into a HTF PD array (a LTF swing
    high inside a 1H FVG = the entry; stop above the intermediate-term high;
    target the HTF opposing array). "this is fractal."
  * **Selling on weakness / buying on strength**: after the Judas sweeps the
    low, place a **buy stop above the high of the candle that swept the low**
    (mirror for shorts); stop below the swept low *with room to breathe*; target
    the HTF premium array. Higher odds of the sweep when **there are no FVGs in
    the lag up** to the swept level.

Owner note (ep 28): turtle soups "are not the highest probability ... if you
just wait there are better entries out there." These detectors are faithful to
the plan, not a claim of edge.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pandas as pd

from atoz.core.fvg import FVG, find_fvgs
from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Candles, Direction, Swing, SwingType
from atoz.liquidity import (
    LiquidityEvent,
    LiquidityPool,
    PoolType,
    classify_pool,
    find_liquidity_pools,
)


# --------------------------------------------------------------------------- #
# Trade object
# --------------------------------------------------------------------------- #


class Quadrant(Enum):
    """Range quadrants (ep 28). Equilibrium = 0.5."""

    DISCOUNT_DISCOUNT = "discount_discount"      # 0.00 - 0.25
    DISCOUNT_PREMIUM = "discount_premium"        # 0.25 - 0.50
    PREMIUM_DISCOUNT = "premium_discount"        # 0.50 - 0.75
    PREMIUM_PREMIUM = "premium_premium"          # 0.75 - 1.00


class TurtleSoupPlan(Enum):
    SEEK_AND_DESTROY = "seek_and_destroy"
    TRENDING_SWEEP = "trending_sweep"            # anticipated sweep into HTF PD array
    BUYING_ON_STRENGTH = "buying_on_strength"    # buy stop above the sweeping candle
    SELLING_ON_WEAKNESS = "selling_on_weakness"  # sell stop below the sweeping candle


@dataclass
class TurtleSoupTrade:
    """A turtle-soup trade produced by one of the ep-28 plans."""

    plan: TurtleSoupPlan
    direction: Direction
    entry: float
    stop: float
    target: float
    swept_pool: LiquidityPool       # the liquidity the Judas swept
    index: int                      # bar the entry confirms
    quadrant: Optional[Quadrant] = None  # seek-and-destroy only

    @property
    def entry_price(self) -> float:
        """Alias for ``entry`` — the entry trigger price."""
        return self.entry

    @property
    def rr(self) -> float:
        risk = abs(self.entry - self.stop)
        return abs(self.target - self.entry) / risk if risk else 0.0


# --------------------------------------------------------------------------- #
# Range + quadrants (ep 28 steps 1-2)
# --------------------------------------------------------------------------- #


@dataclass
class Range:
    """The range we are stuck in, with quadrants (ep 28)."""

    high: float
    low: float
    high_index: int
    low_index: int

    @property
    def equilibrium(self) -> float:
        return (self.high + self.low) / 2.0

    @property
    def q25(self) -> float:
        return self.low + 0.25 * (self.high - self.low)

    @property
    def q75(self) -> float:
        return self.low + 0.75 * (self.high - self.low)

    def quadrant_of(self, price: float) -> Quadrant:
        """Which quadrant a price sits in (ep 28)."""
        if price < self.q25:
            return Quadrant.DISCOUNT_DISCOUNT
        if price < self.equilibrium:
            return Quadrant.DISCOUNT_PREMIUM
        if price < self.q75:
            return Quadrant.PREMIUM_DISCOUNT
        return Quadrant.PREMIUM_PREMIUM


def find_range(df: pd.DataFrame, lookback: int = 100) -> Optional[Range]:
    """Determine the range we are stuck in from the last ``lookback`` bars (the
    highest high to the lowest low) — ep-28 step 1.

    In a true seek-and-destroy condition price oscillates around the 50% of this
    band; the caller supplies the window that visually frames the range.
    """
    if len(df) < 2:
        return None
    window = df.tail(lookback)
    c = Candles.of(window)
    hi_local = int(c.high.argmax())
    lo_local = int(c.low.argmin())
    base = len(df) - len(window)
    return Range(
        high=float(c.high[hi_local]),
        low=float(c.low[lo_local]),
        high_index=base + hi_local,
        low_index=base + lo_local,
    )


# --------------------------------------------------------------------------- #
# ST model — first then second displacement FVG (ep 28 / the ST-model video)
# --------------------------------------------------------------------------- #


def _st_displacement_fvg(
    fvgs: List[FVG],
    direction: Direction,
    after: int,
    window: int,
) -> Optional[FVG]:
    """Return the **second** displacement FVG of the ST model after ``after``
    (ep 28: "we have first displacement lower ... we want a second one ... that
    is exactly what you would want to see").

    The preferred (higher-probability) entry is the second displacement; we
    require at least two same-direction FVGs in the window and return the 2nd.
    """
    legs = [
        f for f in fvgs
        if f.direction is direction and after < f.index <= after + window
    ]
    legs.sort(key=lambda f: f.index)
    if len(legs) >= 2:
        return legs[1]
    return None


# --------------------------------------------------------------------------- #
# Plan A — seek-and-destroy turtle soups
# --------------------------------------------------------------------------- #


def find_seek_and_destroy(
    df: pd.DataFrame,
    rng: Optional[Range] = None,
    range_lookback: int = 100,
    sweep_window: int = 20,
    st_window: int = 15,
    reaction_atr_mult: float = 1.0,
) -> List[TurtleSoupTrade]:
    """Seek-and-destroy turtle soups (ep-28 Plan A).

    Sequence per the transcript: range → quadrants → judas liquidity sweep →
    ST model → entry → close target near equilibrium. We only fire coming off
    **premium-premium** (short) or **discount-discount** (long), and the target
    is the nearest liquidity pool / equilibrium close to EQ — never a large run.
    """
    if rng is None:
        rng = find_range(df, lookback=range_lookback)
    if rng is None:
        return []

    c = Candles.of(df)
    fvgs = find_fvgs(df)
    swings = find_swings(df)
    pools = find_liquidity_pools(df, swings)

    out: List[TurtleSoupTrade] = []

    for pool in pools:
        ev = classify_pool(df, pool, reaction_atr_mult=reaction_atr_mult, window=sweep_window)
        if ev is not LiquidityEvent.SWEEP:
            continue  # need a Judas sweep (take + reject), not a run

        above = pool.kind in (PoolType.EQUAL_HIGHS, PoolType.SINGLE_HIGH)
        # locate the sweep bar (first take after the pool forms)
        sweep_at = None
        for k in range(pool.index + 1, c.n):
            if above and c.high[k] > pool.price:
                sweep_at = k
                break
            if not above and c.low[k] < pool.price:
                sweep_at = k
                break
        if sweep_at is None:
            continue

        quad = rng.quadrant_of(pool.price)
        # short only off premium-premium; long only off discount-discount
        if above:
            if quad is not Quadrant.PREMIUM_PREMIUM:
                continue
            direction = Direction.BEARISH
        else:
            if quad is not Quadrant.DISCOUNT_DISCOUNT:
                continue
            direction = Direction.BULLISH

        # ST model: the SECOND displacement FVG after the sweep (preferred entry)
        disp = _st_displacement_fvg(fvgs, direction, sweep_at, st_window)
        if disp is None:
            continue

        if direction is Direction.BEARISH:
            entry = disp.top
            stop = float(max(c.high[sweep_at:disp.index + 1]))  # above the sweep high
            target = _close_target_below(rng, pools, disp.index, entry)
        else:
            entry = disp.bottom
            stop = float(min(c.low[sweep_at:disp.index + 1]))   # below the sweep low
            target = _close_target_above(rng, pools, disp.index, entry)

        if target is None or abs(entry - stop) < 1e-9:
            continue

        out.append(
            TurtleSoupTrade(
                plan=TurtleSoupPlan.SEEK_AND_DESTROY,
                direction=direction,
                entry=float(entry),
                stop=float(stop),
                target=float(target),
                swept_pool=pool,
                index=disp.c3_index,
                quadrant=quad,
            )
        )

    out.sort(key=lambda t: t.index)
    return out


def _close_target_below(rng: Range, pools: List[LiquidityPool], at: int, entry: float) -> Optional[float]:
    """Close target for a short: a liquidity low between entry and EQ, else EQ
    itself (ep 28 — "a close easy target ... close to equilibrium")."""
    eq = rng.equilibrium
    lows = [
        p.price for p in pools
        if p.kind in (PoolType.EQUAL_LOWS, PoolType.SINGLE_LOW)
        and p.index < at and eq <= p.price < entry
    ]
    if lows:
        return max(lows)            # nearest pool above EQ (don't overshoot)
    if eq < entry:
        return eq
    return None


def _close_target_above(rng: Range, pools: List[LiquidityPool], at: int, entry: float) -> Optional[float]:
    """Close target for a long: a liquidity high between entry and EQ, else EQ."""
    eq = rng.equilibrium
    highs = [
        p.price for p in pools
        if p.kind in (PoolType.EQUAL_HIGHS, PoolType.SINGLE_HIGH)
        and p.index < at and entry < p.price <= eq
    ]
    if highs:
        return min(highs)
    if eq > entry:
        return eq
    return None


# --------------------------------------------------------------------------- #
# Plan B — buying on strength / selling on weakness (ep 28)
# --------------------------------------------------------------------------- #


def _lag_has_fvg(fvgs: List[FVG], direction: Direction, start: int, end: int) -> bool:
    """Whether a same-direction FVG exists in the lag [start, end] (ep 28: the
    odds of a sweep are *increased* when there are **no** FVGs in the lag up)."""
    return any(direction is f.direction and start <= f.index <= end for f in fvgs)


def find_strength_weakness(
    df: pd.DataFrame,
    sweep_window: int = 20,
    reaction_atr_mult: float = 1.0,
    require_no_lag_fvg: bool = True,
) -> List[TurtleSoupTrade]:
    """Buying-on-strength / selling-on-weakness turtle soups (ep-28 Plan B).

    For each swept liquidity pool: place a **buy stop above the high of the
    candle that swept the low** (long) or a **sell stop below the low of the
    candle that swept the high** (short). Stop goes beyond the swept extreme
    *with room to breathe*; target is the opposing PD array (nearest opposing
    swing pool). When ``require_no_lag_fvg`` the setup only fires if there are
    no same-side FVGs in the lag into the level (higher sweep odds, ep 28).
    """
    c = Candles.of(df)
    swings = find_swings(df)
    fvgs = find_fvgs(df)
    pools = find_liquidity_pools(df, swings)

    out: List[TurtleSoupTrade] = []

    for pool in pools:
        ev = classify_pool(df, pool, reaction_atr_mult=reaction_atr_mult, window=sweep_window)
        if ev is not LiquidityEvent.SWEEP:
            continue
        above = pool.kind in (PoolType.EQUAL_HIGHS, PoolType.SINGLE_HIGH)

        sweep_at = None
        for k in range(pool.index + 1, c.n):
            if above and c.high[k] > pool.price:
                sweep_at = k
                break
            if not above and c.low[k] < pool.price:
                sweep_at = k
                break
        if sweep_at is None:
            continue

        # lag into the level: from the pool's defining bar to the sweep bar.
        # bullish setup sweeps a low → we look for a bullish lag-up FVG.
        lag_dir = Direction.BULLISH if not above else Direction.BEARISH
        if require_no_lag_fvg and _lag_has_fvg(fvgs, lag_dir, pool.index, sweep_at):
            continue

        if not above:
            # buying on strength: buy stop above the sweeping candle's high
            plan = TurtleSoupPlan.BUYING_ON_STRENGTH
            direction = Direction.BULLISH
            entry = float(c.high[sweep_at])
            stop = float(c.low[sweep_at])         # below the swept low (intermediate-term low)
            target = _opposing_array_above(pools, sweep_at, entry)
        else:
            plan = TurtleSoupPlan.SELLING_ON_WEAKNESS
            direction = Direction.BEARISH
            entry = float(c.low[sweep_at])
            stop = float(c.high[sweep_at])
            target = _opposing_array_below(pools, sweep_at, entry)

        if target is None or abs(entry - stop) < 1e-9:
            continue

        out.append(
            TurtleSoupTrade(
                plan=plan,
                direction=direction,
                entry=entry,
                stop=stop,
                target=target,
                swept_pool=pool,
                index=sweep_at,
            )
        )

    out.sort(key=lambda t: t.index)
    return out


def _opposing_array_above(pools: List[LiquidityPool], at: int, entry: float) -> Optional[float]:
    """Nearest premium array (swing-high pool) above the long entry (ep 28 — the
    discount-to-premium target)."""
    highs = [
        p.price for p in pools
        if p.kind in (PoolType.EQUAL_HIGHS, PoolType.SINGLE_HIGH)
        and p.index < at and p.price > entry
    ]
    return min(highs) if highs else None


def _opposing_array_below(pools: List[LiquidityPool], at: int, entry: float) -> Optional[float]:
    lows = [
        p.price for p in pools
        if p.kind in (PoolType.EQUAL_LOWS, PoolType.SINGLE_LOW)
        and p.index < at and p.price < entry
    ]
    return max(lows) if lows else None


# --------------------------------------------------------------------------- #
# Convenience
# --------------------------------------------------------------------------- #


def find_turtle_soups(
    df: pd.DataFrame,
    range_lookback: int = 100,
) -> List[TurtleSoupTrade]:
    """Run both ep-28 plans and return all turtle-soup trades, ordered by bar."""
    out = find_seek_and_destroy(df, range_lookback=range_lookback)
    out += find_strength_weakness(df)
    out.sort(key=lambda t: t.index)
    return out

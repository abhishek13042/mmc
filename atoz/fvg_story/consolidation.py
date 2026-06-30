"""Consolidation / Seek-and-Destroy detector (A-Z Guide ep 27).

> "The most dangerous conditions that you can get trapped in as a trending
> trader are seek and destroy conditions... constantly seeking liquidity,
> taking people out of the market, both sides of the market are getting taken
> out."                                                                — ep 27

The transcript's **step-by-step** recipe for spotting consolidation *before* it
happens:

1. **Take both sides of the market in one expansion.**
   > "We took a major sell side liquidity right there... then afterwards we
   > immediately target the opposing liquidity at the highs... so we sweep the
   > lows and then head for the highs in one big expansion higher. In that
   > moment we have taken both sides of the market."

2. **Magnet back to 50% (equilibrium) of that most-recent expansion range.**
   > "If you draw your Fibonacci on that low and that high... like a magnet,
   > price will refer back to the 50% of that most recent range, which is
   > equilibrium... and price will likely consolidate there."

3. **CONFIRM once PD arrays stop following through.**
   > "This is not guaranteed... it is guaranteed once PD arrays stop following
   > through. PD arrays not following through is the most important aspect...
   > the premium arrays are not following through, the discount arrays are not
   > following through... all the wicks, there's no fair value gap anywhere."

4. **OVER once price displaces out of the range (a fresh FVG breaks out) AND PD
   arrays follow through again.**
   > "When price displaces out of the range... a displacement is a fair value
   > gap... ideally something on the higher time frame... and it displaced out
   > of the consolidation — that is exactly when you can look to trade again...
   > the second sign is PD arrays are finally following through."

Pure functions over an OHLC DataFrame (DatetimeIndex; open/high/low/close).
``index`` is the iloc position. No look-ahead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import numpy as np
import pandas as pd

from atoz.core.fvg import FVG, find_fvgs
from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Candles, Direction, Swing, SwingType
from atoz.liquidity.pools import find_liquidity_pools


class Phase(Enum):
    """Per-bar regime label (ep 27)."""

    EXPANSION = "expansion"          # the big both-sides-taken move
    CONSOLIDATION = "consolidation"  # seek-and-destroy: stuck around equilibrium
    TRENDING = "trending"            # PD arrays following through (normal)


def _atr(df: pd.DataFrame, lookback: int = 14) -> float:
    return float((df["high"] - df["low"]).tail(lookback).mean()) or 1e-9


@dataclass
class ExpansionRange:
    """A "take both sides in one expansion" range (ep 27, step 1).

    ``low``/``high`` are the swept extremes; ``equilibrium`` is the 50% magnet.
    """

    low: float
    high: float
    low_index: int      # bar of the swept low
    high_index: int     # bar of the swept high
    start_index: int    # first bar of the expansion leg
    end_index: int      # last bar of the expansion leg (the second side taken)
    direction: Direction  # BULLISH = swept low then ran to high; BEARISH = mirror

    @property
    def equilibrium(self) -> float:
        """50% of the range — equilibrium (ep 27)."""
        return (self.high + self.low) / 2.0

    @property
    def size(self) -> float:
        return self.high - self.low


@dataclass
class ConsolidationZone:
    """A seek-and-destroy consolidation around equilibrium (ep 27)."""

    expansion: ExpansionRange
    start_index: int                 # where price returns to equilibrium
    end_index: Optional[int]         # where it displaces out (None = ongoing)
    top: float                       # range high (the consolidation band)
    bottom: float                    # range low
    confirmed: bool                  # PD arrays stopped following through
    resolved: bool = False           # displaced out + PD arrays follow through
    breakout_fvg: Optional[FVG] = None
    breakout_direction: Optional[Direction] = None

    @property
    def equilibrium(self) -> float:
        return self.expansion.equilibrium


def find_expansion_ranges(
    df: pd.DataFrame,
    swings: Optional[List[Swing]] = None,
    pool_tolerance: float = 0.0005,
    min_atr_mult: float = 3.0,
    max_legs: int = 8,
) -> List[ExpansionRange]:
    """Find "take a major pool, then immediately take the opposite side in one
    expansion" ranges (ep 27, step 1).

    We look for: a **major liquidity pool** taken (a swing extreme / equal
    highs-lows), immediately followed by a single directional expansion (≥
    ``min_atr_mult`` ATR) that takes the *opposing* swing extreme — both sides
    of the market taken in one move.
    """
    if swings is None:
        swings = find_swings(df)
    c = Candles.of(df)
    atr = _atr(df)
    pools = find_liquidity_pools(df, swings, tolerance=pool_tolerance)

    highs = sorted(swing_highs(swings), key=lambda s: s.index)
    lows = sorted(swing_lows(swings), key=lambda s: s.index)

    out: List[ExpansionRange] = []

    # Bullish expansion: a low gets swept, then price runs up and takes a prior high.
    for lo in lows:
        # find the bar that takes this low
        take_lo = None
        for k in range(lo.index + 1, c.n):
            if c.low[k] < lo.price:
                take_lo = k
                break
        if take_lo is None:
            continue
        # the lowest point reached around the sweep
        end_scan = min(c.n, take_lo + max_legs * 3)
        run_low_i = take_lo
        run_low = c.low[take_lo]
        for k in range(take_lo, min(c.n, take_lo + max_legs)):
            if c.low[k] < run_low:
                run_low, run_low_i = c.low[k], k
        # now require an immediate up-expansion taking a prior high
        target_high = next((h for h in highs if h.index < lo.index), None)
        if target_high is None:
            target_high = next((h for h in highs if h.price > c.high[run_low_i]), None)
        if target_high is None:
            continue
        taken_high_i = None
        for k in range(run_low_i + 1, end_scan):
            if c.high[k] > target_high.price:
                taken_high_i = k
                break
        if taken_high_i is None:
            continue
        rng_low = run_low
        rng_high = c.high[taken_high_i]
        if (rng_high - rng_low) >= min_atr_mult * atr:
            out.append(ExpansionRange(
                low=float(rng_low), high=float(rng_high),
                low_index=run_low_i, high_index=taken_high_i,
                start_index=run_low_i, end_index=taken_high_i,
                direction=Direction.BULLISH,
            ))

    # Bearish expansion: a high gets swept, then price runs down and takes a prior low.
    for hi in highs:
        take_hi = None
        for k in range(hi.index + 1, c.n):
            if c.high[k] > hi.price:
                take_hi = k
                break
        if take_hi is None:
            continue
        end_scan = min(c.n, take_hi + max_legs * 3)
        run_high_i = take_hi
        run_high = c.high[take_hi]
        for k in range(take_hi, min(c.n, take_hi + max_legs)):
            if c.high[k] > run_high:
                run_high, run_high_i = c.high[k], k
        target_low = next((l for l in lows if l.index < hi.index), None)
        if target_low is None:
            target_low = next((l for l in lows if l.price < c.low[run_high_i]), None)
        if target_low is None:
            continue
        taken_low_i = None
        for k in range(run_high_i + 1, end_scan):
            if c.low[k] < target_low.price:
                taken_low_i = k
                break
        if taken_low_i is None:
            continue
        rng_high = run_high
        rng_low = c.low[taken_low_i]
        if (rng_high - rng_low) >= min_atr_mult * atr:
            out.append(ExpansionRange(
                low=float(rng_low), high=float(rng_high),
                low_index=taken_low_i, high_index=run_high_i,
                start_index=run_high_i, end_index=taken_low_i,
                direction=Direction.BEARISH,
            ))

    out.sort(key=lambda r: r.end_index)
    # de-dup near-identical ranges (same end bar, overlapping band)
    deduped: List[ExpansionRange] = []
    for r in out:
        if any(d.end_index == r.end_index and abs(d.equilibrium - r.equilibrium) < atr
               for d in deduped):
            continue
        deduped.append(r)
    return deduped


def pd_arrays_following_through(
    df: pd.DataFrame,
    start_index: int,
    end_index: int,
    fvgs: Optional[List[FVG]] = None,
    min_fvg_atr: float = 0.5,
) -> bool:
    """Are PD arrays *following through* over ``[start_index, end_index]``? (ep 27)

    PD arrays follow through when fresh *significant* fair value gaps keep forming
    in the direction of travel (premium arrays push price lower, discount arrays
    push higher). Seek-and-destroy is the opposite: "all the wicks, there's no
    fair value gap anywhere."

    The transcript is explicit that the gap must be *significant* — "not just a
    one minute fair value gap... that is not significant enough." So a gap only
    counts as a follow-through if its height is ≥ ``min_fvg_atr`` ATR; tiny wicky
    gaps do not count (they are the "all wicks" seek-and-destroy texture).

    Returns ``True`` if at least one significant FVG forms inside the window
    (arrays still delivering), ``False`` if the window is wicky with no
    significant FVGs (arrays stalled → seek-and-destroy).
    """
    if fvgs is None:
        fvgs = find_fvgs(df)
    thresh = min_fvg_atr * _atr(df)
    for f in fvgs:
        # middle candle inside the window counts as a delivery in that window
        if start_index <= f.index <= end_index and (f.top - f.bottom) >= thresh:
            return True
    return False


def displaces_out_of_range(
    df: pd.DataFrame,
    top: float,
    bottom: float,
    from_index: int,
    fvgs: Optional[List[FVG]] = None,
    window: int = 60,
) -> Optional[FVG]:
    """Has price *displaced out of the range* with a fresh FVG? (ep 27, step 4)

    > "A displacement is a fair value gap... and it displaced out of the
    > consolidation — that is exactly when you can look to trade again."

    Returns the first FVG after ``from_index`` whose far edge sits *outside*
    [bottom, top] (a bullish FVG breaking above ``top`` or a bearish FVG below
    ``bottom``), or ``None`` if price stays inside the range.
    """
    if fvgs is None:
        fvgs = find_fvgs(df)
    end = from_index + window
    for f in fvgs:
        if f.index <= from_index or f.index > end:
            continue
        if f.direction is Direction.BULLISH and f.bottom >= top:
            return f
        if f.direction is Direction.BEARISH and f.top <= bottom:
            return f
    return None


def find_consolidations(
    df: pd.DataFrame,
    swings: Optional[List[Swing]] = None,
    min_atr_mult: float = 3.0,
    eq_band_atr: float = 1.0,
    settle_window: int = 40,
    breakout_window: int = 80,
) -> List[ConsolidationZone]:
    """Detect seek-and-destroy consolidation zones, step-by-step (ep 27).

    For each both-sides expansion range:

    1. find where price **magnets back to the 50% equilibrium** (within
       ``eq_band_atr`` ATR) — the consolidation start;
    2. mark it **confirmed** when **PD arrays stop following through** over the
       settling window (no fresh FVGs);
    3. mark it **resolved** once price **displaces out** with a fresh FVG *and*
       PD arrays follow through again past that breakout.

    The consolidation band [bottom, top] is taken as the price extremes carved
    out while price hangs around equilibrium (the gray "major consolidation").
    """
    if swings is None:
        swings = find_swings(df)
    c = Candles.of(df)
    atr = _atr(df)
    fvgs = find_fvgs(df)
    ranges = find_expansion_ranges(df, swings, min_atr_mult=min_atr_mult)

    out: List[ConsolidationZone] = []
    for r in ranges:
        eq = r.equilibrium
        band = eq_band_atr * atr

        # 1) first return to equilibrium after the expansion ends
        eq_i = None
        for k in range(r.end_index + 1, min(c.n, r.end_index + settle_window)):
            if c.low[k] <= eq + band and c.high[k] >= eq - band:
                eq_i = k
                break
        if eq_i is None:
            continue

        # consolidation band = extremes while price hangs around eq
        seg_end = min(c.n, eq_i + settle_window)
        top = float(c.high[eq_i:seg_end].max())
        bottom = float(c.low[eq_i:seg_end].min())

        # 2) confirmed when PD arrays stop following through in the settle window
        following = pd_arrays_following_through(df, eq_i, seg_end - 1, fvgs)
        confirmed = not following

        # 3) resolved when price displaces out with a fresh FVG and arrays resume
        breakout = displaces_out_of_range(df, top, bottom, eq_i, fvgs, window=breakout_window)
        resolved = False
        bo_dir = None
        if breakout is not None:
            bo_dir = breakout.direction
            after = min(c.n, breakout.index + 20)
            resolved = pd_arrays_following_through(df, breakout.index, after, fvgs)

        out.append(ConsolidationZone(
            expansion=r,
            start_index=eq_i,
            end_index=breakout.index if breakout is not None else None,
            top=top, bottom=bottom,
            confirmed=confirmed, resolved=resolved,
            breakout_fvg=breakout, breakout_direction=bo_dir,
        ))

    out.sort(key=lambda z: z.start_index)
    return out


def consolidation_flags(
    df: pd.DataFrame,
    zones: Optional[List[ConsolidationZone]] = None,
    only_confirmed: bool = True,
) -> pd.Series:
    """Per-bar boolean: is this bar inside a (confirmed) seek-and-destroy
    consolidation? (ep 27)

    A bar is flagged from a zone's equilibrium-return start up to its breakout
    (or end of data if unresolved). With ``only_confirmed`` we require PD arrays
    to have stopped following through (the transcript's confirmation step).
    """
    if zones is None:
        zones = find_consolidations(df)
    flags = pd.Series(False, index=df.index)
    n = len(df)
    for z in zones:
        if only_confirmed and not z.confirmed:
            continue
        end = z.end_index if z.end_index is not None else n - 1
        lo = max(0, z.start_index)
        hi = min(n - 1, end)
        if lo <= hi:
            flags.iloc[lo:hi + 1] = True
    return flags

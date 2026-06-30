"""Sweep-vs-Run — the FVG "secret story" (A-Z Guide ep 24).

> "A sweep of liquidity is when price takes liquidity and then moves to the
> opposite liquidity. A run on liquidity is when we have buy stops right here
> and price just keeps on going... that story and the differentiator what
> happens between a sweep and a run can be told by fair value gaps alone."
>                                                                       — ep 24

The mechanical rule, stated exactly by the transcript:

> "Whenever we are sweeping liquidity, the fair value gaps that were being
> created pushing into that sweep — they will get disrespected and we will form
> an ST model... whenever we sweep and we immediately completely rebalance a
> fair value gap completely, that is not what you would want to see if you're
> expecting a run."
>
> "A run on liquidity has a high probability of respecting a fair value gap
> that is overlapping with the high or the low that it just swept — and with
> respect I mean that it continues higher off of that fair value gap... we sort
> of have a small staircase higher, we stumble higher."

So, after price **takes a high (or low)**, look at the FVG that *overlaps with
that swept level* (the FVG created on the push into the level):

* **SWEEP**  — that overlapping FVG is **disrespected / immediately completely
  rebalanced**; an ST (sweep) model forms to the opposite side. Price then
  targets *opposing* liquidity (buy-side → sell-side, or vice-versa). Reversal.
* **RUN**    — that overlapping FVG is **respected**: price rejects off it and
  continues in the same direction ("stumble higher"). Continuation.

The transcript's "ST model" is the reversal leg that disrespects the FVG. We
detect it as: price trades back fully through the overlapping FVG (rebalances
it) and closes beyond its far edge, i.e. the FVG no longer holds.

Pure functions over an OHLC DataFrame (DatetimeIndex; open/high/low/close).
``index`` is the iloc position. No look-ahead beyond the bars being classified.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pandas as pd

from atoz.core.fvg import FVG, find_fvgs
from atoz.core.swings import find_swings
from atoz.core.types import Candles, Direction, Swing, SwingType


class StoryType(Enum):
    """What the overlapping FVG tells you happened at a swept level (ep 24)."""

    SWEEP = "sweep"   # FVG disrespected / rebalanced → ST model → reversal
    RUN = "run"       # FVG respected → continuation ("stumble higher")
    NONE = "none"     # level not taken, or no overlapping FVG to read


@dataclass
class OverlapFVG:
    """An FVG that *overlaps with a swept high/low* (the array to read, ep 24)."""

    fvg: FVG
    swing: Swing            # the high/low that was taken
    take_index: int         # bar where the swing level was first taken


@dataclass
class SweepRunSignal:
    """The verdict at one taken level (ep 24)."""

    swing: Swing                 # the high/low that price took
    take_index: int              # bar where it was taken
    fvg: Optional[FVG]           # the overlapping FVG that told the story
    story: StoryType             # SWEEP or RUN
    resolve_index: Optional[int] # bar where the story resolved
    # On a SWEEP, opposing liquidity becomes the draw (ep 24):
    targets_opposing: bool       # True for SWEEP (reversal), False for RUN


def _atr(df: pd.DataFrame, lookback: int = 14) -> float:
    return float((df["high"] - df["low"]).tail(lookback).mean()) or 1e-9


def overlapping_fvg(
    df: pd.DataFrame,
    swing: Swing,
    take_index: int,
    fvgs: Optional[List[FVG]] = None,
) -> Optional[FVG]:
    """Return the FVG that *overlaps with the swept level* (ep 24).

    The relevant FVG is the one "created pushing into that sweep" — i.e. the
    most recent FVG, of the *same polarity as the move that took the level*,
    formed at/before ``take_index`` whose price band straddles the swing price.

    For a taken **high** (bullish push up) we read the **bullish** FVG sitting at
    that high; for a taken **low** (bearish push down) the **bearish** FVG at
    that low.
    """
    if fvgs is None:
        fvgs = find_fvgs(df)

    took_high = swing.kind is SwingType.HIGH
    want = Direction.BULLISH if took_high else Direction.BEARISH

    candidates = [
        f
        for f in fvgs
        if f.direction is want
        and f.c3_index <= take_index            # fully formed before/at the take
        and f.contains(swing.price)             # overlaps the swept level
    ]
    if not candidates:
        # Relax "contains" to "nearest band touching the level" — the FVG can sit
        # just under a high / just above a low (still "overlapping with" it).
        for f in fvgs:
            if f.direction is not want or f.c3_index > take_index:
                continue
            if f.bottom <= swing.price <= f.top:
                candidates.append(f)
    if not candidates:
        return None
    # the one closest to the level (the array immediately defending it)
    return min(candidates, key=lambda f: abs(f.midpoint - swing.price))


def classify_sweep_or_run(
    df: pd.DataFrame,
    swing: Swing,
    take_index: int,
    fvg: FVG,
    window: int = 30,
) -> SweepRunSignal:
    """Classify SWEEP vs RUN from the overlapping FVG's fate (ep 24).

    After the level is taken at ``take_index``, watch the overlapping ``fvg``:

    * **SWEEP** — the FVG is *disrespected / completely rebalanced*: price trades
      fully back through it and closes beyond its far edge (the ST reversal leg).
    * **RUN** — the FVG is *respected*: price reacts off the FVG and continues in
      the original direction (makes a new extreme beyond the taken level) while
      the FVG still holds.

    Whichever happens first within ``window`` bars decides the story.
    """
    c = Candles.of(df)
    took_high = swing.kind is SwingType.HIGH

    end = min(c.n, take_index + 1 + window)
    for k in range(take_index + 1, end):
        if took_high:
            # SWEEP: bullish FVG rebalanced — close back below its bottom.
            if c.close[k] < fvg.bottom:
                return SweepRunSignal(swing, take_index, fvg, StoryType.SWEEP, k, True)
            # RUN: FVG respected and price extends above the taken high.
            if c.low[k] >= fvg.bottom and c.high[k] > swing.price and k > take_index + 1:
                return SweepRunSignal(swing, take_index, fvg, StoryType.RUN, k, False)
        else:
            # SWEEP: bearish FVG rebalanced — close back above its top.
            if c.close[k] > fvg.top:
                return SweepRunSignal(swing, take_index, fvg, StoryType.SWEEP, k, True)
            # RUN: FVG respected and price extends below the taken low.
            if c.high[k] <= fvg.top and c.low[k] < swing.price and k > take_index + 1:
                return SweepRunSignal(swing, take_index, fvg, StoryType.RUN, k, False)

    return SweepRunSignal(swing, take_index, fvg, StoryType.NONE, None, False)


def _first_take(c: Candles, swing: Swing) -> Optional[int]:
    """First bar after the swing where its level is traded through (taken)."""
    for k in range(swing.index + 1, c.n):
        if swing.kind is SwingType.HIGH and c.high[k] > swing.price:
            return k
        if swing.kind is SwingType.LOW and c.low[k] < swing.price:
            return k
    return None


def sweep_run_signals(
    df: pd.DataFrame,
    swings: Optional[List[Swing]] = None,
    window: int = 30,
) -> List[SweepRunSignal]:
    """Read the FVG story at every taken swing high/low across ``df`` (ep 24).

    For each swing that price later takes, find the FVG overlapping that level
    and classify the move as SWEEP or RUN. Only levels that (a) were taken and
    (b) have an overlapping FVG to read produce a signal.
    """
    if swings is None:
        swings = find_swings(df)
    fvgs = find_fvgs(df)
    c = Candles.of(df)

    out: List[SweepRunSignal] = []
    for s in swings:
        take = _first_take(c, s)
        if take is None:
            continue
        fvg = overlapping_fvg(df, s, take, fvgs)
        if fvg is None:
            continue
        sig = classify_sweep_or_run(df, s, take, fvg, window=window)
        if sig.story is not StoryType.NONE:
            out.append(sig)

    out.sort(key=lambda s: s.take_index)
    return out


def expect_sting_only(
    df: pd.DataFrame,
    draw_price: float,
    at_index: int,
    direction: Direction,
    expansion_atr_mult: float = 3.0,
    proximity_atr_mult: float = 2.0,
) -> bool:
    """Should we expect only a *sting* into the first FVG (not a full retrace)? (ep 24)

    > "When we are close to the drawn liquidity and we already had a huge
    > expansion higher, I would not expect price to make a big retracement lower
    > into an overlapping PD array... I would only demand off of price to come
    > into that first fair value gap and then continue."

    Two conditions, both required:

    * **already expanded** — the last ``proximity``-window move toward the draw is
      large (≥ ``expansion_atr_mult`` ATR), and
    * **close to drawn liquidity** — current price is within ``proximity_atr_mult``
      ATR of ``draw_price`` (and the draw not yet taken).

    ``direction`` is the move direction (BULLISH toward a high draw above,
    BEARISH toward a low draw below).
    """
    c = Candles.of(df)
    if at_index <= 0 or at_index >= c.n:
        return False
    atr = _atr(df)

    price = c.close[at_index]
    # draw not yet taken
    if direction is Direction.BULLISH and price >= draw_price:
        return False
    if direction is Direction.BEARISH and price <= draw_price:
        return False

    close_enough = abs(draw_price - price) <= proximity_atr_mult * atr

    look = max(0, at_index - 10)
    if direction is Direction.BULLISH:
        expansion = c.high[at_index] - c.low[look:at_index + 1].min()
    else:
        expansion = c.high[look:at_index + 1].max() - c.low[at_index]
    expanded = expansion >= expansion_atr_mult * atr

    return bool(close_enough and expanded)

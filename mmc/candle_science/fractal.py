"""Fractal (multi-timeframe) candle science (transcript 05 — the heart of it).

A higher-timeframe candle *is* the lower-timeframe order flow that printed
inside it. "If we look at the daily timeframe, then that daily order flow lag is
also one singular candle on a different timeframe." So instead of judging a
candle by its shape, we descend a timeframe and read the order flow lags inside:

* **One-sided** order flow (only bullish OR only bearish lags) → **disrespect**
  candle, continue in that direction.
* **Two-sided** order flow (both bullish *and* bearish lags — a reversal inside
  the candle) → **respect** candle. The respect direction is the *last* order
  flow inside the candle: "first order flow lags going lower to then going
  higher" makes a long wick at the bottom → bullish respect; the mirror (higher
  then lower) makes a long wick at the top → bearish respect.

How the higher-TF candle maps to lower-TF order flow
----------------------------------------------------
Pass the slice of the *lower*-timeframe DataFrame that covers exactly the one
higher-timeframe candle you want to classify. For a daily candle you pass that
day's 1H/15m bars; for a weekly candle you pass that week's daily bars. The
order flow lags found in that slice are read in bar order to decide one-sided
vs two-sided (and, when two-sided, which way the final reversal points).

This reuses :func:`mmc.core.find_order_flow_lags` (which itself requires FVGs —
"no FVG, no order flow lag"), keeping candle science *order-flow native* rather
than reinventing detection.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

from mmc.core.fvg import find_fvgs
from mmc.core.structure import find_order_flow_lags
from mmc.core.swings import find_swings
from mmc.core.types import Direction, OrderFlowLag

from .types import CandleClass, CandleScience


def classify_from_order_flow(
    lower_tf_df: pd.DataFrame,
    *,
    window: int = 3,
) -> Optional[CandleScience]:
    """Classify one higher-TF candle from the lower-TF order flow inside it.

    ``lower_tf_df`` is the lower-timeframe slice that spans exactly the single
    higher-timeframe candle (see module docstring for the mapping). We detect
    swings + FVGs + order flow lags on it and read their polarities in order:

    * all lags the same polarity → **disrespect** in that direction;
    * mixed polarities → **respect**, pointing in the direction of the *last*
      order flow lag inside the candle (the side that "won" the reversal).

    Returns ``None`` when the slice has no order flow lags at all — "no FVG, no
    order flow lag", so there is nothing to read and no classification.

    The geometry ratios on the returned :class:`CandleScience` are computed from
    the slice's overall OHLC (open of the first bar, max high, min low, close of
    the last bar) so the object stays comparable with :func:`classify_candle`.
    """
    lags = order_flow_lags_in(lower_tf_df, window=window)
    if not lags:
        return None

    directions = [lag.direction for lag in lags]
    has_bull = any(d is Direction.BULLISH for d in directions)
    has_bear = any(d is Direction.BEARISH for d in directions)

    if has_bull and has_bear:
        candle_class = CandleClass.RESPECT
        # Continue in the direction of the *last* (most recent) order flow lag.
        direction = lags[-1].direction
    else:
        candle_class = CandleClass.DISRESPECT
        direction = Direction.BULLISH if has_bull else Direction.BEARISH

    body_ratio, upper_ratio, lower_ratio = _slice_ratios(lower_tf_df)
    return CandleScience(
        candle_class=candle_class,
        direction=direction,
        body_ratio=body_ratio,
        upper_wick_ratio=upper_ratio,
        lower_wick_ratio=lower_ratio,
    )


def order_flow_lags_in(
    lower_tf_df: pd.DataFrame,
    *,
    window: int = 3,
) -> List[OrderFlowLag]:
    """Find the order flow lags inside a lower-TF slice, ordered by index.

    Thin convenience over the core pipeline
    (``find_swings`` → ``find_fvgs`` → ``find_order_flow_lags``) so the fractal
    layer never reimplements detection.
    """
    swings = find_swings(lower_tf_df)
    fvgs = find_fvgs(lower_tf_df)
    return find_order_flow_lags(swings, fvgs, window=window)


def _slice_ratios(df: pd.DataFrame) -> tuple[float, float, float]:
    """Body / upper-wick / lower-wick ratios for the candle a slice represents."""
    o = float(df["open"].iloc[0])
    c = float(df["close"].iloc[-1])
    h = float(df["high"].max())
    l = float(df["low"].min())
    rng = h - l
    if rng <= 0:
        return 0.0, 0.0, 0.0
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    return body / rng, upper / rng, lower / rng

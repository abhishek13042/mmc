"""Single-candle classification from geometry (transcript 05 — Candle Science).

A higher-timeframe candle *is* lower-timeframe order flow. Rather than always
descend a timeframe, candle science lets us read the candle's own shape:

* **Disrespect** — body-dominant, one-sided. The wick on the *trend side* (top
  for a bullish candle, bottom for a bearish one) is small. Continue in the
  candle's direction.
* **Respect** — a long wick on one side relative to the body (a reversal inside
  the candle). Long wick at the **bottom** → bullish respect (continue up). Long
  wick at the **top** → bearish respect (continue down).

The classification is driven by two documented thresholds, both expressed as a
fraction of the candle's total range (``high - low``):

* ``respect_wick_ratio`` (default ``0.5``) — a single wick this large or larger
  marks a *respect* candle. A 50% wick is the canonical "long wick" the
  transcript draws.
* ``body_ratio_floor`` (default ``0.0``) — optional minimum body for a candle to
  count as a clean *disrespect* (set > 0 to reject dojis / indecision).

If neither wick reaches ``respect_wick_ratio`` the candle is a *disrespect*
candle and its direction is taken from the body (close vs open); a flat body
falls back to the side with the smaller wick (the disrespect side).
"""

from __future__ import annotations

from typing import List

import pandas as pd

from mmc.core.types import Direction

from .types import CandleClass, CandleScience

DEFAULT_RESPECT_WICK_RATIO = 0.5
DEFAULT_BODY_RATIO_FLOOR = 0.0


def classify_candle(
    open: float,
    high: float,
    low: float,
    close: float,
    *,
    respect_wick_ratio: float = DEFAULT_RESPECT_WICK_RATIO,
    body_ratio_floor: float = DEFAULT_BODY_RATIO_FLOOR,
) -> CandleScience:
    """Classify a single candle from its OHLC geometry (transcript 05).

    Parameters
    ----------
    open, high, low, close
        The candle's prices (``high >= low``).
    respect_wick_ratio
        A wick (as a fraction of range) at or above this marks a *respect*
        candle. The respect direction is *away* from the long wick: a long
        lower wick → bullish, a long upper wick → bearish.
    body_ratio_floor
        Minimum body (fraction of range) for a *disrespect* candle. Below it the
        candle is treated as indecision and labelled *respect* on its larger
        wick. Default ``0.0`` disables this check.

    Returns
    -------
    CandleScience
        The class, implied continuation :class:`Direction`, and the geometry
        ratios that produced the label.
    """
    rng = high - low
    if rng <= 0:
        # Degenerate flat candle: no information. Treat as a bullish disrespect
        # with zero ratios so callers still get a well-formed object.
        return CandleScience(
            candle_class=CandleClass.DISRESPECT,
            direction=Direction.BULLISH if close >= open else Direction.BEARISH,
            body_ratio=0.0,
            upper_wick_ratio=0.0,
            lower_wick_ratio=0.0,
        )

    body = abs(close - open)
    upper_wick = high - max(open, close)
    lower_wick = min(open, close) - low

    body_ratio = body / rng
    upper_wick_ratio = upper_wick / rng
    lower_wick_ratio = lower_wick / rng

    longest_wick_ratio = max(upper_wick_ratio, lower_wick_ratio)
    is_respect = longest_wick_ratio >= respect_wick_ratio or (
        body_ratio < body_ratio_floor
    )

    if is_respect:
        # Continue away from the long wick: long bottom wick -> bullish.
        direction = (
            Direction.BULLISH
            if lower_wick_ratio >= upper_wick_ratio
            else Direction.BEARISH
        )
        candle_class = CandleClass.RESPECT
    else:
        candle_class = CandleClass.DISRESPECT
        if close > open:
            direction = Direction.BULLISH
        elif close < open:
            direction = Direction.BEARISH
        else:
            # Flat body, short wicks: continue toward the side with the
            # smaller wick (the disrespected / trend side).
            direction = (
                Direction.BULLISH
                if upper_wick_ratio <= lower_wick_ratio
                else Direction.BEARISH
            )

    return CandleScience(
        candle_class=candle_class,
        direction=direction,
        body_ratio=body_ratio,
        upper_wick_ratio=upper_wick_ratio,
        lower_wick_ratio=lower_wick_ratio,
    )


def classify_candles(
    df: pd.DataFrame,
    *,
    respect_wick_ratio: float = DEFAULT_RESPECT_WICK_RATIO,
    body_ratio_floor: float = DEFAULT_BODY_RATIO_FLOOR,
) -> List[CandleScience]:
    """Vectorized :func:`classify_candle` over an OHLC DataFrame.

    Returns one :class:`CandleScience` per row, in bar order. The DataFrame must
    have ``open``/``high``/``low``/``close`` columns (the standard MMC OHLC
    frame, see ARCHITECTURE.md).
    """
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    return [
        classify_candle(
            float(o[i]),
            float(h[i]),
            float(l[i]),
            float(c[i]),
            respect_wick_ratio=respect_wick_ratio,
            body_ratio_floor=body_ratio_floor,
        )
        for i in range(len(df))
    ]


def next_candle_direction(science: CandleScience) -> Direction:
    """Implied next-candle continuation direction (transcript 05).

    Both candle kinds resolve to the same rule once classified: continue in the
    candle's :attr:`CandleScience.direction` — i.e. in the disrespect candle's
    own direction, or in the direction of the respect (away from the long wick).
    """
    return science.direction

"""Tests for the candle science layer (transcript 05).

Covers the four geometric classifications (bullish/bearish disrespect and
bullish/bearish respect) with hand-crafted candles, the next-candle direction
helper, and a fractal case where a lower-TF DataFrame's order flow drives the
label.
"""

from mmc.candle_science import (
    CandleClass,
    classify_candle,
    classify_candles,
    classify_from_order_flow,
    next_candle_direction,
    order_flow_lags_in,
)
from mmc.core.types import Direction


# --------------------------------------------------------------------------- #
# Geometric classification — the four candle kinds
# --------------------------------------------------------------------------- #


def test_bullish_disrespect():
    # Up candle, body-dominant, small wick at the top.
    # open=10 close=19, high=20 low=9.5 -> range 10.5, body 9, top wick 1.
    cs = classify_candle(open=10.0, high=20.0, low=9.5, close=19.0)
    assert cs.candle_class is CandleClass.DISRESPECT
    assert cs.direction is Direction.BULLISH
    assert cs.is_bullish and cs.is_disrespect
    assert cs.label == "bullish disrespect"
    # body dominates; both wicks are small.
    assert cs.body_ratio > 0.5
    assert cs.upper_wick_ratio < 0.5 and cs.lower_wick_ratio < 0.5


def test_bearish_disrespect():
    # Down candle, body-dominant, small wick at the bottom.
    cs = classify_candle(open=19.0, high=19.5, low=9.0, close=10.0)
    assert cs.candle_class is CandleClass.DISRESPECT
    assert cs.direction is Direction.BEARISH
    assert cs.label == "bearish disrespect"
    assert cs.lower_wick_ratio < 0.5


def test_bullish_respect_long_bottom_wick():
    # Long wick at the BOTTOM -> bullish respect (continue up, away from wick).
    # open=18 close=19, high=20 low=10 -> range 10, lower wick 8 (=0.8).
    cs = classify_candle(open=18.0, high=20.0, low=10.0, close=19.0)
    assert cs.candle_class is CandleClass.RESPECT
    assert cs.direction is Direction.BULLISH
    assert cs.label == "bullish respect"
    assert cs.lower_wick_ratio >= 0.5
    assert cs.lower_wick_ratio > cs.upper_wick_ratio


def test_bearish_respect_long_top_wick():
    # Long wick at the TOP -> bearish respect (continue down, away from wick).
    cs = classify_candle(open=12.0, high=20.0, low=10.0, close=11.0)
    assert cs.candle_class is CandleClass.RESPECT
    assert cs.direction is Direction.BEARISH
    assert cs.label == "bearish respect"
    assert cs.upper_wick_ratio >= 0.5
    assert cs.upper_wick_ratio > cs.lower_wick_ratio


def test_respect_wick_ratio_threshold_is_tunable():
    # A 40% lower wick is a disrespect at the default 0.5 threshold...
    candle = dict(open=14.0, high=20.0, low=10.0, close=18.0)
    default = classify_candle(**candle)
    assert default.candle_class is CandleClass.DISRESPECT
    # ...but a respect once we lower the threshold below the wick ratio.
    tuned = classify_candle(**candle, respect_wick_ratio=0.3)
    assert tuned.candle_class is CandleClass.RESPECT
    assert tuned.direction is Direction.BULLISH


def test_body_ratio_floor_demotes_doji_to_respect():
    # Tiny body, modest wicks: with a body floor it becomes a respect candle.
    cs = classify_candle(
        open=15.0, high=20.0, low=10.0, close=15.2, body_ratio_floor=0.1
    )
    assert cs.candle_class is CandleClass.RESPECT


def test_next_candle_direction_continues_in_classified_direction():
    bull = classify_candle(open=10.0, high=20.0, low=9.5, close=19.0)
    bear = classify_candle(open=12.0, high=20.0, low=10.0, close=11.0)
    assert next_candle_direction(bull) is Direction.BULLISH
    assert next_candle_direction(bear) is Direction.BEARISH


def test_classify_candles_vectorized(make_ohlc):
    df = make_ohlc(
        [
            (10.0, 20.0, 9.5, 19.0),  # bullish disrespect
            (19.0, 19.5, 9.0, 10.0),  # bearish disrespect
            (18.0, 20.0, 10.0, 19.0),  # bullish respect (long bottom wick)
        ]
    )
    out = classify_candles(df)
    assert len(out) == 3
    assert out[0].candle_class is CandleClass.DISRESPECT and out[0].is_bullish
    assert out[1].candle_class is CandleClass.DISRESPECT and out[1].is_bearish
    assert out[2].candle_class is CandleClass.RESPECT and out[2].is_bullish


# --------------------------------------------------------------------------- #
# Fractal classification — lower-TF order flow drives the label
# --------------------------------------------------------------------------- #


def _bullish_order_flow_slice(make_ohlc):
    """A lower-TF slice with a swing low followed by a bullish FVG.

    Bars: a swing low at index 2 (low 1.0, with higher lows either side), then a
    3-candle bullish FVG (c2 closes above c1.high, c3.low stays above c1.high).
    """
    return make_ohlc(
        [
            (5.0, 5.5, 3.0, 5.0),    # 0
            (5.0, 5.2, 2.0, 4.0),    # 1  (c1 of FVG: high = 5.2)
            (4.0, 4.5, 1.0, 4.2),    # 2  swing low (low 1.0 < neighbours)
            (4.2, 9.0, 4.0, 8.5),    # 3  c2: closes 8.5 > c1.high 5.2 (expansion)
            (8.5, 10.0, 6.0, 9.0),   # 4  c3: low 6.0 > c1.high 5.2 -> bullish FVG
        ]
    )


def _bearish_order_flow_slice(make_ohlc):
    """A lower-TF slice with a swing high followed by a bearish FVG."""
    return make_ohlc(
        [
            (5.0, 7.0, 6.5, 6.0),    # 0
            (6.0, 8.0, 6.0, 7.0),    # 1  (c1 of FVG: low = 6.0)
            (7.0, 9.0, 6.5, 7.5),    # 2  swing high (high 9.0 > neighbours)
            (7.5, 7.6, 2.0, 2.5),    # 3  c2: closes 2.5 < c1.low 6.0 (expansion)
            (2.5, 5.0, 1.0, 3.0),    # 4  c3: high 5.0 < c1.low 6.0 -> bearish FVG
        ]
    )


def test_fractal_one_sided_bullish_is_disrespect(make_ohlc):
    df = _bullish_order_flow_slice(make_ohlc)
    lags = order_flow_lags_in(df)
    assert lags, "expected at least one bullish order flow lag in the slice"
    assert all(lag.direction is Direction.BULLISH for lag in lags)

    cs = classify_from_order_flow(df)
    assert cs is not None
    assert cs.candle_class is CandleClass.DISRESPECT
    assert cs.direction is Direction.BULLISH
    assert next_candle_direction(cs) is Direction.BULLISH


def test_fractal_one_sided_bearish_is_disrespect(make_ohlc):
    df = _bearish_order_flow_slice(make_ohlc)
    lags = order_flow_lags_in(df)
    assert lags
    assert all(lag.direction is Direction.BEARISH for lag in lags)

    cs = classify_from_order_flow(df)
    assert cs is not None
    assert cs.candle_class is CandleClass.DISRESPECT
    assert cs.direction is Direction.BEARISH


def test_fractal_two_sided_is_respect(make_ohlc):
    # Concatenate a bearish-then-bullish order flow so the candle reverses up:
    # first lags go lower, then higher -> long wick at the bottom -> bullish
    # respect (continue in the direction of the LAST order flow).
    bear = _bearish_order_flow_slice(make_ohlc)
    bull = _bullish_order_flow_slice(make_ohlc)
    import pandas as pd

    df = pd.concat([bear, bull], ignore_index=False)
    df.index = pd.date_range("2024-01-01", periods=len(df), freq="1min")

    lags = order_flow_lags_in(df)
    dirs = {lag.direction for lag in lags}
    assert Direction.BULLISH in dirs and Direction.BEARISH in dirs

    cs = classify_from_order_flow(df)
    assert cs is not None
    assert cs.candle_class is CandleClass.RESPECT
    # Last order flow inside the candle is bullish -> continue up.
    assert cs.direction is Direction.BULLISH


def test_fractal_no_order_flow_returns_none(make_ohlc):
    # Flat, structureless data: no FVG -> no order flow lag -> no classification.
    df = make_ohlc([(1.0, 1.1, 0.9, 1.0)] * 4)
    assert order_flow_lags_in(df) == []
    assert classify_from_order_flow(df) is None

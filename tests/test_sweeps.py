"""Tests for the sweeps layer — liquidity sweep vs run, PCH/PCL, order-flow and
candle-science sweeps (transcript 08)."""

from mmc.core import Direction, SwingType, find_fvgs, find_swings, mark_mitigation
from mmc.core.types import SwingPoint
from mmc.sweeps import (
    LiquidityEvent,
    candle_science_sweeps,
    classify_liquidity,
    liquidity_sweeps,
    mark_swept_swings,
    order_flow_sweeps,
    previous_candle_high,
    previous_candle_low,
)


# --------------------------------------------------------------------------- #
# PCH / PCL helpers
# --------------------------------------------------------------------------- #


def test_pch_pcl_basic(make_ohlc):
    df = make_ohlc([
        (1.0, 2.0, 0.5, 1.5),
        (1.5, 3.0, 1.0, 2.5),
        (2.5, 4.0, 2.0, 3.5),
    ])
    # PCH/PCL for bar 1 == high/low of bar 0
    assert previous_candle_high(df, 1) == 2.0
    assert previous_candle_low(df, 1) == 0.5
    assert previous_candle_high(df, 2) == 3.0
    assert previous_candle_low(df, 2) == 1.0


def test_pch_pcl_first_bar_is_none(make_ohlc):
    df = make_ohlc([(1.0, 2.0, 0.5, 1.5), (1.5, 3.0, 1.0, 2.5)])
    assert previous_candle_high(df, 0) is None
    assert previous_candle_low(df, 0) is None


# --------------------------------------------------------------------------- #
# Liquidity sweep vs run
# --------------------------------------------------------------------------- #


def test_sweep_of_swing_high(make_ohlc):
    # Bars 0-2 build a swing high at bar 1 (high = 5).
    # Bar 3 trades above the swing high (high = 6) = the take.
    # Then an aggressive opposing (bearish) FVG forms: bar 4 expansion candle
    # closes below bar 3's low, bar 5 high stays below bar 3's low. Not
    # comfortable above the high -> SWEEP.
    df = make_ohlc([
        (3.0, 4.0, 2.5, 3.5),   # 0
        (3.5, 5.0, 3.0, 4.8),   # 1: swing high (high = 5)
        (4.8, 4.9, 3.5, 4.0),   # 2
        (4.5, 6.0, 4.4, 5.0),   # 3: trades ABOVE 5 (take of liquidity)
        (5.0, 5.1, 1.0, 1.2),   # 4: bearish expansion, close 1.2 < bar3 low 4.4
        (1.2, 1.5, 0.5, 0.8),   # 5: high 1.5 < bar3 low 4.4 -> bearish FVG
    ])
    swings = find_swings(df)
    high = next(s for s in swings if s.kind is SwingType.HIGH and s.index == 1)
    res = classify_liquidity(df, high)
    assert res.event is LiquidityEvent.SWEEP
    assert res.is_sweep
    assert res.break_index == 3
    assert res.signal_fvg is not None
    assert res.signal_fvg.direction is Direction.BEARISH
    assert res.reversal_direction is Direction.BEARISH


def test_run_of_swing_high(make_ohlc):
    # Build a swing high at bar 1 (high = 5). Price trades above it and KEEPS
    # GOING (a bullish/continuation expansion forms). Comfortable -> RUN.
    df = make_ohlc([
        (3.0, 4.0, 2.5, 3.5),   # 0
        (3.5, 5.0, 3.0, 4.8),   # 1: swing high (high = 5)
        (4.8, 4.9, 4.0, 4.2),   # 2
        (4.2, 6.0, 4.1, 5.8),   # 3: trades above 5 (take)
        (6.0, 9.0, 5.9, 8.8),   # 4: bullish expansion, close 8.8 > bar3 high 6.0
        (8.8, 9.5, 7.0, 9.2),   # 5: low 7.0 > bar3 high 6.0 -> bullish FVG
    ])
    swings = find_swings(df)
    high = next(s for s in swings if s.kind is SwingType.HIGH and s.index == 1)
    res = classify_liquidity(df, high)
    assert res.event is LiquidityEvent.RUN
    assert res.is_run
    assert res.break_index == 3
    # signal FVG (if any) is same-direction continuation, not opposing.
    if res.signal_fvg is not None:
        assert res.signal_fvg.direction is Direction.BULLISH
    assert res.reversal_direction is None


def test_level_never_taken_is_none(make_ohlc):
    # Swing high at bar 1 (high = 5) is never traded above afterwards.
    df = make_ohlc([
        (3.0, 4.0, 2.5, 3.5),   # 0
        (3.5, 5.0, 3.0, 4.8),   # 1: swing high
        (4.8, 4.9, 4.0, 4.2),   # 2
        (4.2, 4.5, 3.0, 3.2),   # 3: stays below 5
    ])
    swings = find_swings(df)
    high = next(s for s in swings if s.kind is SwingType.HIGH and s.index == 1)
    res = classify_liquidity(df, high)
    assert res.event is LiquidityEvent.NONE
    assert res.break_index is None


def test_mark_swept_swings_sets_flags(make_ohlc):
    df = make_ohlc([
        (3.0, 4.0, 2.5, 3.5),
        (3.5, 5.0, 3.0, 4.8),   # 1: swing high
        (4.8, 4.9, 3.5, 4.0),
        (4.5, 6.0, 4.4, 5.0),   # 3: take
        (5.0, 5.1, 1.0, 1.2),   # 4: bearish expansion
        (1.2, 1.5, 0.5, 0.8),   # 5
    ])
    swings = find_swings(df)
    mark_swept_swings(df, swings)
    swept = [s for s in swings if s.swept]
    assert any(s.index == 1 and s.sweep_index == 3 for s in swept)
    classifications = liquidity_sweeps(df, swings)
    assert any(c.swing.index == 1 for c in classifications)


# --------------------------------------------------------------------------- #
# Order flow sweep
# --------------------------------------------------------------------------- #


def test_order_flow_sweep_leaves_swing_behind(make_ohlc):
    # A bullish FVG forms, then price stings back into it (mitigates it), leaves
    # behind a swing low, and the rejection fails to make a new bullish FVG
    # within the window -> that swing low is the order-flow sweep level.
    df = make_ohlc([
        (1.0, 1.2, 0.9, 1.1),    # 0  c1 of bullish FVG (high = 1.2)
        (1.1, 2.5, 1.1, 2.4),    # 1  c2 expansion up (close 2.4 > c1 high 1.2)
        (2.4, 2.6, 1.5, 2.0),    # 2  c3 low 1.5 > c1 high 1.2 -> bullish FVG [1.2,1.5]
        (2.0, 2.1, 1.0, 1.3),    # 3  stings into gap (low 1.0 <= top 1.5) mitigates
        (1.3, 1.4, 0.8, 1.0),    # 4  swing low candidate (low 0.8)
        (1.0, 1.6, 0.95, 1.5),   # 5  rejection up but NO new bullish FVG
        (1.5, 1.7, 1.2, 1.45),   # 6
    ])
    swings = find_swings(df)
    fvgs = find_fvgs(df)
    mark_mitigation(df, fvgs)
    sweeps = order_flow_sweeps(df, swings, fvgs, window=4)
    assert sweeps, "expected an order-flow sweep"
    s0 = sweeps[0]
    assert s0.direction is Direction.BULLISH
    assert s0.swing.kind is SwingType.LOW
    assert s0.mitigated_fvg.mitigated
    assert s0.level == s0.swing.price


# --------------------------------------------------------------------------- #
# Candle science sweep (PCH / PCL)
# --------------------------------------------------------------------------- #


def test_candle_science_sweep_pcl(make_ohlc):
    # Bullish FVG, then first candle into it does NOT reject (closes down), and
    # the next candle wicks below that first candle's low (PCL sweep) and closes
    # up -> candle-science sweep continuing higher.
    df = make_ohlc([
        (1.0, 1.2, 0.9, 1.1),    # 0  c1 (high = 1.2)
        (1.1, 2.5, 1.1, 2.4),    # 1  c2 expansion up
        (2.4, 2.6, 1.5, 2.0),    # 2  c3 -> bullish FVG [1.2, 1.5]
        (1.5, 1.5, 1.2, 1.25),   # 3  first candle into gap, bearish (no reject up)
        (1.25, 2.0, 1.0, 1.9),   # 4  wicks below bar3 low 1.2 (PCL) and closes up
    ])
    fvgs = find_fvgs(df)
    sweeps = candle_science_sweeps(df, fvgs)
    assert sweeps, "expected a candle-science sweep"
    cs = sweeps[0]
    assert cs.direction is Direction.BULLISH
    assert cs.kind is SwingType.LOW
    assert cs.level_index == 3
    assert cs.sweep_index == 4
    # the swept level is bar 3's low (the previous candle low)
    assert cs.level == 1.2

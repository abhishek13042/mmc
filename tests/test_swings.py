"""Tests for swing point detection (transcript 01)."""

from mmc.core.swings import find_swings, swing_highs, swing_lows
from mmc.core.types import SwingType


def test_single_swing_high(make_ohlc):
    # middle bar (index 1) pokes above its neighbours -> swing high
    df = make_ohlc([
        (1, 2, 0.5, 1.5),
        (1.5, 3, 1.0, 2.5),   # highest high
        (2.5, 2, 1.0, 1.2),
    ])
    swings = find_swings(df)
    highs = swing_highs(swings)
    assert len(highs) == 1
    assert highs[0].index == 1
    assert highs[0].kind is SwingType.HIGH
    assert highs[0].price == 3
    assert highs[0].is_premium is True


def test_single_swing_low(make_ohlc):
    df = make_ohlc([
        (2, 2.5, 1.5, 2.0),
        (2.0, 2.2, 0.5, 1.0),  # lowest low
        (1.0, 2.0, 1.2, 1.8),
    ])
    lows = swing_lows(find_swings(df))
    assert len(lows) == 1
    assert lows[0].index == 1
    assert lows[0].kind is SwingType.LOW
    assert lows[0].price == 0.5
    assert lows[0].is_premium is False


def test_edges_have_no_swing(make_ohlc):
    # monotonic data: no interior bar is both-sided extreme
    df = make_ohlc([(i, i + 1, i - 1, i + 0.5) for i in range(5)])
    assert swing_highs(find_swings(df)) == []


def test_swings_sorted_by_index(make_ohlc):
    df = make_ohlc([
        (1, 3, 0.5, 2),    # 0
        (2, 2, 0.2, 1),    # 1 swing low
        (1, 5, 0.8, 4),    # 2 swing high
        (4, 4, 1.0, 2),    # 3
    ])
    swings = find_swings(df)
    idxs = [s.index for s in swings]
    assert idxs == sorted(idxs)

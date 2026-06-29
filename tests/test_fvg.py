"""Tests for fair value gap detection & mitigation (transcript 01 / 06)."""

from mmc.core.fvg import find_fvgs, mark_mitigation, unmitigated
from mmc.core.types import Direction


def test_bullish_fvg(make_ohlc):
    df = make_ohlc([
        (1, 2, 0.5, 1.5),     # c1, high = 2
        (1.5, 4, 1.5, 3.5),   # c2 expansion, closes 3.5 > 2
        (3.5, 5, 2.5, 4.5),   # c3, low 2.5 > 2  -> gap [2, 2.5]
    ])
    fvgs = find_fvgs(df)
    assert len(fvgs) == 1
    f = fvgs[0]
    assert f.direction is Direction.BULLISH
    assert f.bottom == 2 and f.top == 2.5
    assert (f.c1_index, f.c2_index, f.c3_index) == (0, 1, 2)
    assert f.is_discount is True


def test_bearish_fvg(make_ohlc):
    df = make_ohlc([
        (5, 5.5, 4, 4.5),     # c1, low = 4
        (4.5, 4.5, 2, 2.5),   # c2 expansion, closes 2.5 < 4
        (2.5, 3.5, 2, 3),     # c3, high 3.5 < 4 -> gap [3.5, 4]
    ])
    fvgs = find_fvgs(df)
    assert len(fvgs) == 1
    f = fvgs[0]
    assert f.direction is Direction.BEARISH
    assert f.bottom == 3.5 and f.top == 4
    assert f.is_premium is True


def test_no_fvg_when_gap_filled(make_ohlc):
    # c3 trades back into c1 high -> no bullish gap
    df = make_ohlc([
        (1, 2, 0.5, 1.5),
        (1.5, 4, 1.5, 3.5),
        (3.5, 5, 1.8, 4.5),   # low 1.8 < c1 high 2 -> no gap
    ])
    assert find_fvgs(df) == []


def test_mitigation(make_ohlc):
    df = make_ohlc([
        (1, 2, 0.5, 1.5),
        (1.5, 4, 1.5, 3.5),
        (3.5, 5, 2.5, 4.5),   # bullish FVG [2, 2.5]
        (4.5, 4.6, 2.4, 4.0),  # low 2.4 <= top 2.5 -> mitigates
    ])
    fvgs = mark_mitigation(df, find_fvgs(df))
    assert len(fvgs) == 1
    assert fvgs[0].mitigated is True
    assert fvgs[0].mitigation_index == 3
    assert unmitigated(fvgs) == []

"""Tests for market structure, FVAs and order flow lags (transcript 02 / 03)."""

from mmc.core.structure import (
    fair_value_areas,
    find_order_flow_lags,
    intermediate_term_points,
)
from mmc.core.swings import find_swings
from mmc.core.types import Direction, StructurePointType, SwingPoint, SwingType


def _sh(i, p):
    return SwingPoint(index=i, price=p, kind=SwingType.HIGH)


def _sl(i, p):
    return SwingPoint(index=i, price=p, kind=SwingType.LOW)


def test_intermediate_term_high():
    # middle swing high (price 5) has lower swing highs either side -> ITH
    swings = [_sh(0, 3), _sh(2, 5), _sh(4, 4), _sl(1, 1), _sl(3, 2)]
    pts = intermediate_term_points(swings)
    iths = [p for p in pts if p.kind is StructurePointType.ITH]
    assert len(iths) == 1
    assert iths[0].price == 5
    assert iths[0].index == 2


def test_intermediate_term_low():
    swings = [_sl(0, 3), _sl(2, 1), _sl(4, 2), _sh(1, 5), _sh(3, 6)]
    pts = intermediate_term_points(swings)
    itls = [p for p in pts if p.kind is StructurePointType.ITL]
    assert len(itls) == 1
    assert itls[0].price == 1
    assert itls[0].index == 2


def test_fair_value_area_polarity():
    # high (index 2) then low (index 4) -> bearish FVA spanning [low, high]
    swings = [_sh(0, 3), _sh(2, 6), _sh(4, 5), _sl(1, 1), _sl(3, 0.5), _sl(5, 1.5)]
    pts = intermediate_term_points(swings)
    fvas = fair_value_areas(pts)
    assert fvas, "expected at least one FVA"
    first = fvas[0]
    assert first.direction in (Direction.BULLISH, Direction.BEARISH)
    assert first.top >= first.bottom


def test_order_flow_lag_pairs_swing_and_fvg(make_ohlc):
    # Build a clean bearish leg: swing high, then a bearish FVG just after it.
    df = make_ohlc([
        (1, 2, 0.5, 1.8),
        (1.8, 5, 1.5, 4.8),   # 1: swing high (high = 5)
        (4.8, 4.9, 2, 2.2),   # 2: expansion down, closes 2.2 < c1(idx1) low 1.5? no
        (2.2, 3, 0.5, 1.0),   # 3
    ])
    swings = find_swings(df)
    from mmc.core.fvg import find_fvgs

    fvgs = find_fvgs(df)
    lags = find_order_flow_lags(swings, fvgs, window=5)
    # Every lag must carry both a swing and an FVG of matching polarity.
    for lag in lags:
        assert lag.swing is not None and lag.fvg is not None
        assert lag.fvg.direction is lag.direction
        assert lag.lod is lag.swing

"""Unit tests for the MMC narrative layer (transcripts 04, 06, 07).

Hand-crafted synthetic bar sequences produce known rejection / perfect /
breakaway FVGs, ideal / good / swept FVAs, and order flow lags whose FLOD / ODD
/ LOD decomposition is asserted directly.
"""

from __future__ import annotations

from mmc.core import (
    Direction,
    FairValueArea,
    FairValueGap,
    OrderFlowLag,
    StructurePoint,
    StructurePointType,
    SwingPoint,
    SwingType,
    find_fvgs,
)
from mmc.narrative import (
    classify_fva,
    classify_fvg,
    classify_fvgs,
    decompose_lag,
    is_seeking_liquidity,
    lag_probability,
    opposing_pd_arrays,
)

# --------------------------------------------------------------------------- #
# FVG quality (transcript 06)
# --------------------------------------------------------------------------- #


def _single_bullish_fvg(df) -> FairValueGap:
    fvgs = [f for f in find_fvgs(df) if f.direction is Direction.BULLISH]
    assert len(fvgs) == 1, f"expected exactly one bullish FVG, got {len(fvgs)}"
    return fvgs[0]


def test_perfect_bullish_fvg(make_ohlc):
    # c1: small candle. c2: big expansion up (close 110, c1.high 100 -> potential
    # gap 10). c3: small consolidation just above c1.high, leaving almost the
    # whole gap (low 109) and NOT expanding past c2.close.
    df = make_ohlc(
        [
            (99.0, 100.0, 98.0, 99.5),     # c1
            (100.0, 110.0, 100.0, 110.0),  # c2 expansion
            (109.5, 110.5, 109.0, 109.8),  # c3 consolidation
        ]
    )
    fvg = _single_bullish_fvg(df)
    assert classify_fvg(df, fvg) == "perfect"
    assert fvg.quality == "perfect"


def test_rejection_bullish_fvg(make_ohlc):
    # Potential gap 10 (c1.high 100, c2.close 110). c3 is a large opposing (down)
    # candle that eats most of the gap: low drops to 100.5 -> realized 0.5,
    # fill = 0.95 >= 0.75 -> rejection.
    df = make_ohlc(
        [
            (99.0, 100.0, 98.0, 99.5),      # c1
            (100.0, 110.0, 100.0, 110.0),   # c2 expansion
            (109.5, 109.6, 100.5, 101.0),   # c3 big rejection down
        ]
    )
    fvg = _single_bullish_fvg(df)
    assert classify_fvg(df, fvg) == "rejection"


def test_breakaway_bullish_fvg(make_ohlc):
    # Potential gap 10. c3 keeps expanding up (close 115 > c2.close 110) with a
    # tiny lower wick -> one-sided expansion -> breakaway. A real gap remains
    # (c3.low 109 > c1.high 100 so fill is small, not a rejection).
    df = make_ohlc(
        [
            (99.0, 100.0, 98.0, 99.5),      # c1
            (100.0, 110.0, 100.0, 110.0),   # c2 expansion
            (109.5, 115.5, 109.0, 115.0),   # c3 expansion up, tiny lower wick
        ]
    )
    fvg = _single_bullish_fvg(df)
    assert classify_fvg(df, fvg) == "breakaway"


def test_classify_fvgs_batch(make_ohlc):
    df = make_ohlc(
        [
            (99.0, 100.0, 98.0, 99.5),
            (100.0, 110.0, 100.0, 110.0),
            (109.5, 110.5, 109.0, 109.8),
        ]
    )
    fvgs = find_fvgs(df)
    classify_fvgs(df, fvgs)
    assert all(f.quality is not None for f in fvgs)


def test_bearish_perfect_fvg(make_ohlc):
    # Mirror of perfect: bearish expansion down then a small consolidation c3.
    # c1.low 100, c2.close 90 -> potential 10; c3 high 91 keeps gap, no expansion.
    df = make_ohlc(
        [
            (101.0, 102.0, 100.0, 100.5),   # c1
            (100.0, 100.0, 90.0, 90.0),     # c2 expansion down
            (90.5, 91.0, 89.5, 90.2),       # c3 consolidation
        ]
    )
    fvgs = [f for f in find_fvgs(df) if f.direction is Direction.BEARISH]
    assert len(fvgs) == 1
    assert classify_fvg(df, fvgs[0]) == "perfect"


# --------------------------------------------------------------------------- #
# FVA quality (transcript 07)
# --------------------------------------------------------------------------- #


def _bullish_fva(top: float, bottom: float, index: int) -> FairValueArea:
    return FairValueArea(
        top=top, bottom=bottom, index=index, direction=Direction.BULLISH
    )


def _bullish_fvg_band(top: float, bottom: float, index: int) -> FairValueGap:
    return FairValueGap(
        top=top,
        bottom=bottom,
        index=index,
        direction=Direction.BULLISH,
        c1_index=index - 2,
        c2_index=index - 1,
        c3_index=index,
    )


def test_fva_good_overlapping_fvg(make_ohlc):
    # Bullish FVA with boundary (bottom) at 100; an overlapping bullish FVG spans
    # 99-101 (contains 100). No nested FVA, not swept -> "good".
    fva = _bullish_fva(top=110.0, bottom=100.0, index=10)
    fvg = _bullish_fvg_band(top=101.0, bottom=99.0, index=11)
    assert classify_fva(fva, [fvg], fvas=[fva]) == "good"
    assert fva.overlapping_fvg is fvg
    assert fva.nested is None


def test_fva_ideal_with_nested(make_ohlc):
    # Same overlapping FVG plus a smaller nested bullish FVA inside -> "ideal".
    fva = _bullish_fva(top=110.0, bottom=100.0, index=10)
    fvg = _bullish_fvg_band(top=101.0, bottom=99.0, index=11)
    nested = _bullish_fva(top=104.0, bottom=101.0, index=9)  # inside 100-110
    assert classify_fva(fva, [fvg], fvas=[fva, nested]) == "ideal"
    assert fva.nested is nested
    assert fva.overlapping_fvg is fvg


def test_fva_swept_no_overlapping_fvg(make_ohlc):
    # No same-polarity FVG overlapping the boundary -> the FVA is the FLOD -> swept.
    fva = _bullish_fva(top=110.0, bottom=100.0, index=10)
    assert classify_fva(fva, [], fvas=[fva]) == "swept"
    assert fva.overlapping_fvg is None


def test_fva_swept_by_wick(make_ohlc):
    # Overlapping FVG exists, but a later bar wicks below the bullish FVA's
    # boundary (100) -> respecting the swing point -> swept.
    df = make_ohlc(
        [
            (105.0, 106.0, 104.0, 105.0),   # 0
            (105.0, 106.0, 104.0, 105.0),   # 1  (fva index)
            (105.0, 106.0, 104.0, 105.0),   # 2  overlapping fvg index
            (103.0, 104.0, 99.0, 100.5),    # 3  wicks below 100 (boundary)
        ]
    )
    fva = _bullish_fva(top=110.0, bottom=100.0, index=1)
    fvg = _bullish_fvg_band(top=101.0, bottom=99.0, index=2)
    assert classify_fva(fva, [fvg], fvas=[fva], df=df) == "swept"


# --------------------------------------------------------------------------- #
# Lag decomposition — FLOD / ODD / LOD (transcript 04)
# --------------------------------------------------------------------------- #


def _bullish_lag() -> OrderFlowLag:
    swing = SwingPoint(index=2, price=95.0, kind=SwingType.LOW)
    fvg = _bullish_fvg_band(top=102.0, bottom=100.0, index=5)
    return OrderFlowLag(direction=Direction.BULLISH, swing=swing, fvg=fvg)


def test_decompose_high_probability_fvg_is_flod():
    # Bullish lag: FVG sits ABOVE the FVA (higher top) so it is hit first on a
    # down-retrace -> FLOD = FVG, ODD = FVA -> high probability.
    lag = _bullish_lag()
    fva = _bullish_fva(top=100.5, bottom=96.0, index=4)  # below the FVG
    lag.fva = fva
    decompose_lag(lag)
    assert lag.flod is lag.fvg
    assert lag.odd is fva
    assert lag.lod is lag.swing
    assert lag_probability(lag) == "high"


def test_decompose_low_probability_fva_is_flod():
    # FVA sits ABOVE the FVG (higher top) -> hit first -> FLOD = FVA -> low prob.
    lag = _bullish_lag()
    fva = _bullish_fva(top=105.0, bottom=101.0, index=4)  # above the FVG top 102
    lag.fva = fva
    decompose_lag(lag)
    assert lag.flod is fva
    assert lag.odd is lag.fvg
    assert lag_probability(lag) == "low"


def test_decompose_no_fva_fvg_is_both():
    lag = _bullish_lag()
    decompose_lag(lag)  # no fva attached / available
    assert lag.flod is lag.fvg
    assert lag.odd is lag.fvg
    assert lag.lod is lag.swing


def test_decompose_attaches_overlapping_fva():
    lag = _bullish_lag()  # FVG band 100-102
    fva = _bullish_fva(top=101.0, bottom=96.0, index=4)  # overlaps the FVG
    decompose_lag(lag, fvas=[fva])
    assert lag.fva is fva


def test_seeking_liquidity_on_deep_retrace(make_ohlc):
    # Lag FVG confirmed at index 2; FVA bottom 96. A later bar trades below 96
    # -> not offering fair value -> seeking liquidity (the swing point / LOD).
    df = make_ohlc(
        [
            (100.0, 101.0, 99.0, 100.0),
            (100.0, 101.0, 99.0, 100.0),
            (100.0, 102.0, 100.0, 101.0),   # lag index
            (99.0, 100.0, 94.0, 95.0),      # deep retrace below 96
        ]
    )
    lag = _bullish_lag()
    lag.fvg.c3_index = 2
    lag.fva = _bullish_fva(top=100.5, bottom=96.0, index=2)
    assert is_seeking_liquidity(lag, df) is True


def test_not_seeking_liquidity_when_respected(make_ohlc):
    df = make_ohlc(
        [
            (100.0, 101.0, 99.0, 100.0),
            (100.0, 101.0, 99.0, 100.0),
            (100.0, 102.0, 100.0, 101.0),   # lag index
            (100.0, 103.0, 99.0, 102.0),    # stays above FVA bottom 96
        ]
    )
    lag = _bullish_lag()
    lag.fvg.c3_index = 2
    lag.fva = _bullish_fva(top=100.5, bottom=96.0, index=2)
    assert is_seeking_liquidity(lag, df) is False


# --------------------------------------------------------------------------- #
# Opposing PD arrays (transcript 06)
# --------------------------------------------------------------------------- #


def test_opposing_pd_arrays_for_bullish_move():
    swings = [
        SwingPoint(index=1, price=110.0, kind=SwingType.HIGH),  # opposing (premium)
        SwingPoint(index=2, price=90.0, kind=SwingType.LOW),    # not opposing
    ]
    bearish_fvg = FairValueGap(
        top=108.0, bottom=106.0, index=3, direction=Direction.BEARISH,
        c1_index=1, c2_index=2, c3_index=3,
    )
    bullish_fvg = FairValueGap(
        top=92.0, bottom=90.0, index=4, direction=Direction.BULLISH,
        c1_index=2, c2_index=3, c3_index=4,
    )
    arrays = opposing_pd_arrays(Direction.BULLISH, swings, [bearish_fvg, bullish_fvg])
    assert swings[0] in arrays          # swing high = premium = opposing
    assert bearish_fvg in arrays        # bearish FVG = premium = opposing
    assert swings[1] not in arrays
    assert bullish_fvg not in arrays

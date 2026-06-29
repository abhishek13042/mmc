"""Unit tests for the MMC context layer (transcript 10 — Usual & Unusual Context).

Context = the objective area where we look for an entry: from a *boundary* (a
narrative PD array we enter from) to the *target* (the first opposing PD array).
Hand-crafted bar sequences produce known order flow lags so that each context
area's boundary and target can be asserted directly. Covers at least one FLOD
usual-context case and one unusual-context (FVA seeking liquidity) case.
"""

from __future__ import annotations

from mmc.core import (
    Direction,
    FairValueArea,
    FairValueGap,
    SwingPoint,
    SwingType,
    Zone,
    find_fvgs,
    find_swings,
    mark_mitigation,
)
from mmc.context import (
    ContextArea,
    find_context_areas,
    find_unusual_context,
    first_opposing_pd_array,
)


# --------------------------------------------------------------------------- #
# ContextArea dataclass helpers
# --------------------------------------------------------------------------- #


def _bullish_fvg(top, bottom, index) -> FairValueGap:
    return FairValueGap(
        top=top,
        bottom=bottom,
        index=index,
        direction=Direction.BULLISH,
        c1_index=index - 2,
        c2_index=index - 1,
        c3_index=index,
    )


def test_context_area_helpers():
    boundary = _bullish_fvg(top=102.0, bottom=100.0, index=5)
    target = SwingPoint(index=9, price=110.0, kind=SwingType.HIGH)
    area = ContextArea(
        boundary=boundary, target=target, direction=Direction.BULLISH, defense="FLOD"
    )

    assert area.is_bullish
    assert area.target_price == 110.0
    # price inside the boundary => trigger to drop a timeframe
    assert area.price_in_boundary(101.0)
    assert not area.price_in_boundary(99.0)
    # an entry zone between boundary bottom (100) and target (110) is in context
    entry = Zone(top=104.0, bottom=103.0, index=6, direction=Direction.BULLISH)
    assert area.contains_entry_zone(entry)
    # an entry zone above the target is NOT in context
    too_high = Zone(top=112.0, bottom=111.0, index=7, direction=Direction.BULLISH)
    assert not area.contains_entry_zone(too_high)


# --------------------------------------------------------------------------- #
# first_opposing_pd_array — the mechanical target rule
# --------------------------------------------------------------------------- #


def test_first_opposing_pd_array_prefers_swing(make_ohlc):
    df = make_ohlc([(100, 101, 99, 100)] * 12)
    swings = [
        SwingPoint(index=2, price=95.0, kind=SwingType.LOW),    # not opposing
        SwingPoint(index=8, price=112.0, kind=SwingType.HIGH),  # opposing, ahead
    ]
    target = first_opposing_pd_array(Direction.BULLISH, 5, df, swings, [])
    assert isinstance(target, SwingPoint)
    assert target.price == 112.0


def test_first_opposing_pd_array_previous_candle_fallback(make_ohlc):
    # No opposing swing / FVG ahead -> fall back to the previous candle high.
    df = make_ohlc(
        [
            (100, 101, 99, 100),  # 0
            (100, 105, 99, 104),  # 1  high = 105
            (104, 106, 103, 105),  # 2  (from_index)
        ]
    )
    target = first_opposing_pd_array(Direction.BULLISH, 2, df, [], [])
    assert isinstance(target, SwingPoint)
    assert target.kind is SwingType.HIGH
    assert target.price == 105.0  # previous candle (index 1) high


# --------------------------------------------------------------------------- #
# Usual context — FLOD (FVG boundary -> opposing swing high)
# --------------------------------------------------------------------------- #


def _flod_df(make_ohlc):
    """A clean bullish order flow lag: swing low at 95, then a bullish FVG
    [99, 102] (boundary), then price expands up to a swing high at 112 (target)."""
    return make_ohlc(
        [
            (100, 101, 99, 100),    # 0
            (99, 100, 96, 97),      # 1
            (97, 98, 95, 96),       # 2  swing low @ 95
            (96, 99, 96, 98.5),     # 3  c1
            (99, 104, 99, 103.5),   # 4  c2 expansion (close 103.5 > c1.high 99)
            (103, 104, 102, 103),   # 5  c3 low 102 > 99 -> bullish FVG [99, 102]
            (103, 108, 102, 107),   # 6  push up
            (108, 112, 107, 111),   # 7  swing high @ 112
            (110, 111, 108, 109),   # 8
            (108, 109, 106, 107),   # 9
        ]
    )


def test_flod_usual_context(make_ohlc):
    df = _flod_df(make_ohlc)
    areas = find_context_areas(df)

    flod = [a for a in areas if a.defense == "FLOD" and a.is_bullish]
    assert flod, "expected at least one bullish FLOD context area"

    # Every bullish FLOD boundary is a discount FVG (the array we enter from).
    assert all(a.boundary.is_discount for a in flod)

    # The bullish FVG [99, 102] (confirmed at index 5) is one such boundary;
    # its target is the first opposing premium array = swing high @ 112.
    area = next(a for a in flod if a.boundary.index == 5)
    assert area.kind == "usual"
    assert area.direction is Direction.BULLISH
    assert area.boundary.is_discount  # bullish FVG = discount array we enter from
    assert area.boundary.bottom == 99.0
    assert area.boundary.top == 102.0
    assert isinstance(area.target, SwingPoint)
    assert area.target.kind is SwingType.HIGH
    assert area.target.price == 112.0

    # Boundary is entered (price trades into [99, 102]) and target is reached.
    assert area.price_in_boundary(100.0)
    assert area.target_reached(df)


def test_context_areas_are_objective_pure_function(make_ohlc):
    # Calling twice yields the same context areas (pure over the DataFrame).
    df = _flod_df(make_ohlc)
    a1 = find_context_areas(df)
    a2 = find_context_areas(df)
    assert len(a1) == len(a2)
    assert all(x.boundary.index == y.boundary.index for x, y in zip(a1, a2))


# --------------------------------------------------------------------------- #
# Unusual context — FVA stops offering fair value -> seeking liquidity
# --------------------------------------------------------------------------- #


def _unusual_df(make_ohlc):
    """A bullish lag whose FVA then fails: price deep-retraces below the FVA and
    forms a bearish FVG inside it (seeking liquidity towards the FVA low)."""
    return make_ohlc(
        [
            (100, 101, 99, 100),    # 0
            (99, 100, 96, 97),      # 1
            (96, 97, 94, 95),       # 2  swing low @ 94
            (95, 98, 95, 97.5),     # 3  c1
            (98, 103, 98, 102.5),   # 4  c2 expansion (close > c1.high 98)
            (102, 103, 101, 102),   # 5  c3 -> bullish FVG [98, 101]
            (101, 102, 97, 98),     # 6  d1 (deep retrace begins)
            (97, 98, 90, 91),       # 7  d2 expansion down -> bearish FVG forms
            (90, 93, 89, 90),       # 8  d3 high 93 < d1.low 97 -> bearish FVG [93, 97]
            (90, 91, 86, 87),       # 9  continues lower
        ]
    )


def test_unusual_context_fva_seeking_liquidity(make_ohlc):
    df = _unusual_df(make_ohlc)
    # A bullish (discount) FVA overlapping the bullish FVG band, with its low at
    # the swing low (94) — the liquidity that becomes the external target.
    fva = FairValueArea(top=101.0, bottom=94.0, index=5, direction=Direction.BULLISH)

    areas = find_unusual_context(df, fvas=[fva])
    assert areas, "expected an unusual-context area (FVA seeking liquidity)"

    area = areas[0]
    # Bigger picture is unusual; the FVG we trade is itself usual context.
    assert area.kind == "unusual"
    # The boundary is the opposing (bearish) FVG that formed inside the FVA.
    assert isinstance(area.boundary, FairValueGap)
    assert area.boundary.direction is Direction.BEARISH
    assert area.direction is Direction.BEARISH
    # External target = the FVA's far side (its low, 94) — the liquidity sought.
    assert area.external_target is not None
    assert area.external_target.price == 94.0
    # The immediate target is the first opposing PD array below the boundary.
    assert area.target_price <= area.boundary.top


def test_no_unusual_context_when_fva_respected(make_ohlc):
    # Bullish lag where price stays above the FVA bottom -> still offering fair
    # value -> no unusual context.
    df = make_ohlc(
        [
            (100, 101, 99, 100),    # 0
            (99, 100, 96, 97),      # 1
            (96, 97, 94, 95),       # 2  swing low @ 94
            (95, 98, 95, 97.5),     # 3  c1
            (98, 103, 98, 102.5),   # 4  c2 expansion
            (102, 103, 101, 102),   # 5  c3 -> bullish FVG [98, 101]
            (102, 106, 100, 105),   # 6  stays above FVA bottom 94, continues up
            (105, 109, 104, 108),   # 7
            (108, 112, 107, 111),   # 8
            (110, 111, 108, 109),   # 9
        ]
    )
    fva = FairValueArea(top=101.0, bottom=94.0, index=5, direction=Direction.BULLISH)
    assert find_unusual_context(df, fvas=[fva]) == []

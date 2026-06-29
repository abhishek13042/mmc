"""Unit tests for the MMC entry layer (transcript 11 — Entries using Order Flow).

Entries happen **inside a context area** and are all about fair value gaps. We
hand-craft an entry-timeframe bar sequence containing a clear bearish sharp turn
(a bullish FVG *into* the boundary -> a bearish FVG *out* of it) so the resulting
:class:`Entry`'s direction, entry zone, stop loss and 1:2 take profit can be
asserted directly. Also covers time-frame alignment and the RR math helpers.
"""

from __future__ import annotations

import pytest

from mmc.core import (
    Direction,
    FairValueGap,
    OrderFlowLag,
    SwingPoint,
    SwingType,
    Timeframe,
    Zone,
    find_fvgs,
    find_swings,
)
from mmc.context import ContextArea
from mmc.entry import (
    BASELINE_ORDER_FLOW,
    BASELINE_SHARP_TURN,
    Entry,
    find_entries,
    find_sharp_turns,
    is_valid_alignment,
    make_stop_loss,
    make_take_profit,
    should_move_to_breakeven,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _bearish_fvg(top, bottom, index) -> FairValueGap:
    return FairValueGap(
        top=top,
        bottom=bottom,
        index=index,
        direction=Direction.BEARISH,
        c1_index=index - 2,
        c2_index=index - 1,
        c3_index=index,
    )


def _bearish_context() -> ContextArea:
    """A bearish context area: premium boundary up at 110-112, target low at 90."""
    boundary = _bearish_fvg(top=112.0, bottom=110.0, index=2)
    target = SwingPoint(index=40, price=90.0, kind=SwingType.LOW)
    return ContextArea(
        boundary=boundary,
        target=target,
        direction=Direction.BEARISH,
        defense="FLOD",
    )


def _sharp_turn_df(make_ohlc):
    """An entry-TF sequence with a bearish sharp turn inside the bearish context.

    Layout (bars 0..):
      * an up leg that prints a *bullish* FVG into the boundary band (the trap);
      * a swing high at the top;
      * a sharp drop printing a *bearish* FVG (the continuation we enter on),
        whose preceding swing high forms the order flow lag.
    """
    bars = [
        # idx 0-2: up leg printing a bullish FVG that stings into the boundary.
        (100.0, 101.0, 100.0, 101.0),   # 0  c1
        (101.5, 109.0, 101.5, 108.5),   # 1  c2 expansion (closes above c1 high)
        (109.0, 111.5, 110.5, 111.0),   # 2  c3 low 110.5 > c1 high 101 -> bull FVG; into boundary[110,112]
        # idx 3: swing-high candle (the lag swing high) at 112.5.
        (111.0, 112.5, 109.5, 109.8),   # 3  swing high 112.5
        # idx 4-6: sharp drop -> the bearish "FVG out" (continuation) below boundary.
        (109.8, 110.0, 108.0, 108.2),   # 4  c1 (low 108)
        (108.0, 108.2, 101.0, 101.5),   # 5  c2 expansion (closes below c1 low 108)
        (101.5, 107.5, 101.0, 103.0),   # 6  c3 high 107.5 < c1 low 108 -> bear FVG out
        # idx 7+: continue lower toward the target.
        (103.0, 103.5, 98.0, 98.5),     # 7
        (98.5, 99.0, 93.0, 93.5),       # 8
        (93.5, 94.0, 90.0, 90.5),       # 9
    ]
    return make_ohlc(bars)


# --------------------------------------------------------------------------- #
# Sharp-turn entry detection
# --------------------------------------------------------------------------- #


def test_sharp_turn_entry(make_ohlc):
    df = _sharp_turn_df(make_ohlc)
    ctx = _bearish_context()

    entries = find_sharp_turns(ctx, df, rr=2.0)
    assert entries, "expected at least one sharp-turn entry"
    e = entries[0]

    # Direction matches the (bearish) context.
    assert e.direction is Direction.BEARISH
    assert e.entry_type == "sharp_turn"

    # Entry zone is the bearish FVG-out at [108.2, 109.5], below the boundary.
    assert e.entry_zone.direction is Direction.BEARISH
    assert e.entry_zone.bottom == pytest.approx(108.2)
    assert e.entry_zone.top == pytest.approx(109.5)
    assert e.entry_zone.top < ctx.boundary.bottom  # "out of" the boundary

    # Entry price is the near edge in the trade's favour (the FVG top, 109.5).
    assert e.entry_price == pytest.approx(109.5)

    # Stop loss is ABOVE the most recent order flow lag's swing high.
    assert e.lag is not None
    assert e.stop_loss > e.entry_price
    assert e.stop_loss == pytest.approx(e.lag.swing.price)
    assert e.stop_loss >= e.lag.swing.price  # beyond the lag

    # Take profit is a 1:2 RR below entry.
    assert e.take_profit < e.entry_price
    assert e.reward == pytest.approx(2.0 * e.risk)
    assert e.take_profit == pytest.approx(e.entry_price - 2.0 * e.risk)

    # The entry FVG lies inside the context area.
    assert ctx.contains_entry_zone(e.entry_zone)


def test_sharp_turn_fast_quality(make_ohlc):
    df = _sharp_turn_df(make_ohlc)
    ctx = _bearish_context()
    e = find_sharp_turns(ctx, df, rr=2.0)[0]

    # Faster turn (fewer bars between in/out) -> flagged higher quality.
    assert e.bars_to_turn is not None
    assert e.bars_to_turn > 0
    assert e.fast is True  # few bars between the trap and the continuation


def test_find_entries_dispatch(make_ohlc):
    df = _sharp_turn_df(make_ohlc)
    ctx = _bearish_context()
    via_top = find_entries(ctx, df, entry_type="sharp_turn", rr=2.0)
    direct = find_sharp_turns(ctx, df, rr=2.0)
    assert len(via_top) == len(direct) == 1


def test_find_entries_killzone_gate(make_ohlc):
    df = _sharp_turn_df(make_ohlc)
    ctx = _bearish_context()
    # The synthetic index starts at 2024-01-01 00:00 (minute bars), which is
    # OUTSIDE the forex kill zone (02:00-10:00 NY) -> entries filtered out.
    gated = find_entries(ctx, df, entry_type="sharp_turn", killzone="forex")
    assert gated == []
    # Without the gate, the entry is present.
    assert find_entries(ctx, df, entry_type="sharp_turn") != []


# --------------------------------------------------------------------------- #
# Time-frame alignment
# --------------------------------------------------------------------------- #


def test_alignment_baseline_ok():
    # Sharp turn: daily ctx -> 1H baseline is valid.
    assert BASELINE_SHARP_TURN[Timeframe.D1] is Timeframe.H1
    assert is_valid_alignment(Timeframe.D1, Timeframe.H1, "sharp_turn")
    # Order flow: daily ctx -> 15m baseline is valid.
    assert BASELINE_ORDER_FLOW[Timeframe.D1] is Timeframe.M15
    assert is_valid_alignment(Timeframe.D1, Timeframe.M15, "order_flow")


def test_alignment_going_higher_ok():
    # Going *higher* than the baseline (closer to context TF) is allowed:
    # daily ctx sharp turn baseline is 1H; H4 is higher and still <= D1 -> ok.
    assert is_valid_alignment(Timeframe.D1, Timeframe.H4, "sharp_turn")


def test_alignment_going_lower_rejected():
    # Going *lower* than the baseline is rejected:
    # daily ctx sharp turn baseline is 1H; M15/M5 are below it -> invalid.
    assert not is_valid_alignment(Timeframe.D1, Timeframe.M15, "sharp_turn")
    assert not is_valid_alignment(Timeframe.D1, Timeframe.M5, "sharp_turn")


def test_alignment_entry_tf_above_context_rejected():
    # An entry TF above the context TF makes no sense.
    assert not is_valid_alignment(Timeframe.H1, Timeframe.H4, "sharp_turn")


# --------------------------------------------------------------------------- #
# RR math helpers
# --------------------------------------------------------------------------- #


def test_make_take_profit_bearish():
    # Stop above entry (bearish) -> TP a 1:2 RR below.
    tp = make_take_profit(entry_price=104.0, stop_loss=106.0, rr=2.0)
    assert tp == pytest.approx(104.0 - 2.0 * 2.0)  # risk=2 -> reward=4 -> 100.0


def test_make_take_profit_bullish():
    # Stop below entry (bullish) -> TP a 1:2 RR above.
    tp = make_take_profit(entry_price=100.0, stop_loss=98.0, rr=2.0)
    assert tp == pytest.approx(100.0 + 2.0 * 2.0)  # 104.0


def test_make_take_profit_custom_rr():
    tp = make_take_profit(entry_price=100.0, stop_loss=98.0, rr=3.0)
    assert tp == pytest.approx(106.0)


def test_make_stop_loss_polarity():
    lag_high = OrderFlowLag(
        direction=Direction.BEARISH,
        swing=SwingPoint(index=3, price=112.0, kind=SwingType.HIGH),
        fvg=_bearish_fvg(top=104.0, bottom=103.0, index=6),
    )
    sl = make_stop_loss(lag_high, Direction.BEARISH)
    assert sl == pytest.approx(112.0)  # above the lag high

    lag_low = OrderFlowLag(
        direction=Direction.BULLISH,
        swing=SwingPoint(index=3, price=90.0, kind=SwingType.LOW),
        fvg=FairValueGap(
            top=95.0, bottom=94.0, index=6, direction=Direction.BULLISH,
            c1_index=4, c2_index=5, c3_index=6,
        ),
    )
    sl_b = make_stop_loss(lag_low, Direction.BULLISH)
    assert sl_b == pytest.approx(90.0)  # below the lag low


def test_entry_risk_reward_helpers():
    ctx = _bearish_context()
    fvg = _bearish_fvg(top=104.0, bottom=103.0, index=6)
    lag = OrderFlowLag(
        direction=Direction.BEARISH,
        swing=SwingPoint(index=3, price=106.0, kind=SwingType.HIGH),
        fvg=fvg,
    )
    sl = make_stop_loss(lag, Direction.BEARISH)            # 106
    tp = make_take_profit(104.0, sl, rr=2.0)               # 104 - 2*2 = 100
    e = Entry(
        direction=Direction.BEARISH,
        entry_zone=fvg,
        stop_loss=sl,
        take_profit=tp,
        context=ctx,
        entry_type="sharp_turn",
        index=6,
        lag=lag,
        rr=2.0,
    )
    assert e.entry_price == pytest.approx(104.0)
    assert e.risk == pytest.approx(2.0)
    assert e.reward == pytest.approx(4.0)
    assert e.realized_rr == pytest.approx(2.0)


def test_should_move_to_breakeven():
    ctx = _bearish_context()
    entry_fvg = _bearish_fvg(top=104.0, bottom=103.0, index=6)
    e = Entry(
        direction=Direction.BEARISH,
        entry_zone=entry_fvg,
        stop_loss=106.0,
        take_profit=100.0,
        context=ctx,
        entry_type="sharp_turn",
        index=6,
    )
    # No later lag -> no break-even yet.
    assert should_move_to_breakeven(e, None) is False
    # A new bearish lag whose FVG is below the entry -> no reason to return.
    later = OrderFlowLag(
        direction=Direction.BEARISH,
        swing=SwingPoint(index=8, price=100.0, kind=SwingType.HIGH),
        fvg=_bearish_fvg(top=99.0, bottom=98.0, index=10),
    )
    assert should_move_to_breakeven(e, later) is True

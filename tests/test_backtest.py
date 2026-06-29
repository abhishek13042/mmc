"""Unit tests for the MMC backtest layer (the trade simulator on top of entries).

We hand-build real :class:`mmc.entry.Entry` signals with known entry / stop /
target levels and craft deterministic OHLC bars that produce a clean WIN, a clean
LOSS, an ambiguous same-bar SL/TP resolution, a NO_FILL and a TIMEOUT. Then we
assert the per-trade outcomes, realised R, and the aggregate statistics
(win rate, expectancy, profit factor, equity curve). All P/L is in R-multiples
(``R = |entry - stop|``).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from mmc.core import Direction, FairValueGap, SwingPoint, SwingType, Timeframe, Zone
from mmc.context import ContextArea
from mmc.data import DEFAULT_DATA_DIR
from mmc.entry import Entry
from mmc.backtest import (
    BacktestResult,
    Outcome,
    Trade,
    backtest_symbol,
    run_backtest,
    simulate_entry,
)


# --------------------------------------------------------------------------- #
# Builders for deterministic, hand-made entries
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


def _context(direction: Direction) -> ContextArea:
    """A minimal context area (only used to satisfy the Entry dataclass)."""
    if direction is Direction.BEARISH:
        boundary = _bearish_fvg(top=112.0, bottom=110.0, index=0)
        target = SwingPoint(index=99, price=90.0, kind=SwingType.LOW)
    else:
        boundary = _bullish_fvg(top=92.0, bottom=90.0, index=0)
        target = SwingPoint(index=99, price=110.0, kind=SwingType.HIGH)
    return ContextArea(boundary=boundary, target=target, direction=direction)


def _bearish_entry(index: int = 2, rr: float = 2.0) -> Entry:
    """Bearish entry: enter at FVG top 100, stop 102 (risk=2), TP 96 (1:2)."""
    fvg = _bearish_fvg(top=100.0, bottom=99.0, index=index)
    return Entry(
        direction=Direction.BEARISH,
        entry_zone=fvg,
        stop_loss=102.0,
        take_profit=96.0,
        context=_context(Direction.BEARISH),
        entry_type="sharp_turn",
        index=index,
        rr=rr,
    )


def _bullish_entry(index: int = 2, rr: float = 2.0) -> Entry:
    """Bullish entry: enter at FVG bottom 100, stop 98 (risk=2), TP 104 (1:2)."""
    fvg = _bullish_fvg(top=101.0, bottom=100.0, index=index)
    return Entry(
        direction=Direction.BULLISH,
        entry_zone=fvg,
        stop_loss=98.0,
        take_profit=104.0,
        context=_context(Direction.BULLISH),
        entry_type="sharp_turn",
        index=index,
        rr=rr,
    )


# --------------------------------------------------------------------------- #
# Entry-price sanity (the fill model's reference levels)
# --------------------------------------------------------------------------- #


def test_entry_levels():
    e = _bearish_entry()
    assert e.entry_price == pytest.approx(100.0)  # FVG top for a bearish trade
    assert e.risk == pytest.approx(2.0)
    assert e.take_profit == pytest.approx(96.0)

    b = _bullish_entry()
    assert b.entry_price == pytest.approx(100.0)  # FVG bottom for a bullish trade
    assert b.risk == pytest.approx(2.0)
    assert b.take_profit == pytest.approx(104.0)


# --------------------------------------------------------------------------- #
# Deterministic WIN
# --------------------------------------------------------------------------- #


def test_bearish_win(make_ohlc):
    # Bearish entry @100, stop 102, TP 96. Bars: stay away, fill, then drop to TP.
    bars = [
        (95.0, 96.0, 94.0, 95.5),     # 0  (entry confirmed here, index=2 below)
        (95.0, 96.0, 94.0, 95.5),     # 1
        (95.0, 96.0, 94.0, 95.5),     # 2  entry.index (skipped: fill starts at 3)
        (97.0, 100.5, 96.5, 99.0),    # 3  high 100.5 >= 100 -> FILL (no SL/TP this bar)
        (99.0, 99.5, 95.5, 96.5),     # 4  low 95.5 <= 96 -> TP hit (stop 102 untouched)
    ]
    df = make_ohlc(bars)
    trade = simulate_entry(_bearish_entry(index=2), df)
    assert trade.outcome is Outcome.WIN
    assert trade.fill_index == 3
    assert trade.fill_price == pytest.approx(100.0)
    assert trade.exit_index == 4
    assert trade.exit_price == pytest.approx(96.0)
    assert trade.r_multiple == pytest.approx(2.0)  # 1:2 win
    assert trade.ambiguous is False


def test_bullish_win(make_ohlc):
    # Bullish entry @100, stop 98, TP 104. Fill on a dip, then rally to TP.
    bars = [
        (105.0, 106.0, 104.5, 105.5),  # 0
        (105.0, 106.0, 104.5, 105.5),  # 1
        (105.0, 106.0, 104.5, 105.5),  # 2  entry.index
        (103.0, 103.5, 99.5, 101.0),   # 3  low 99.5 <= 100 -> FILL
        (101.0, 104.5, 100.5, 104.0),  # 4  high 104.5 >= 104 -> TP (stop 98 untouched)
    ]
    df = make_ohlc(bars)
    trade = simulate_entry(_bullish_entry(index=2), df)
    assert trade.outcome is Outcome.WIN
    assert trade.r_multiple == pytest.approx(2.0)


# --------------------------------------------------------------------------- #
# Deterministic LOSS
# --------------------------------------------------------------------------- #


def test_bearish_loss(make_ohlc):
    # Bearish entry @100, stop 102. Fill, then rally through the stop.
    bars = [
        (95.0, 96.0, 94.0, 95.5),      # 0
        (95.0, 96.0, 94.0, 95.5),      # 1
        (95.0, 96.0, 94.0, 95.5),      # 2  entry.index
        (97.0, 100.5, 96.5, 99.5),     # 3  high 100.5 -> FILL (stop 102 not yet)
        (99.5, 102.5, 99.0, 101.5),    # 4  high 102.5 >= 102 -> STOP (TP 96 untouched)
    ]
    df = make_ohlc(bars)
    trade = simulate_entry(_bearish_entry(index=2), df)
    assert trade.outcome is Outcome.LOSS
    assert trade.exit_price == pytest.approx(102.0)
    assert trade.r_multiple == pytest.approx(-1.0)
    assert trade.ambiguous is False


# --------------------------------------------------------------------------- #
# Ambiguous same-bar SL + TP -> conservative LOSS
# --------------------------------------------------------------------------- #


def test_ambiguous_same_bar_resolves_as_loss(make_ohlc):
    # The fill bar's range spans BOTH the stop (102) and the target (96).
    bars = [
        (95.0, 96.0, 94.0, 95.5),      # 0
        (95.0, 96.0, 94.0, 95.5),      # 1
        (95.0, 96.0, 94.0, 95.5),      # 2  entry.index
        (99.0, 103.0, 95.0, 98.0),     # 3  high 103 >= 102 AND low 95 <= 96 -> ambiguous
    ]
    df = make_ohlc(bars)
    trade = simulate_entry(_bearish_entry(index=2), df)
    assert trade.outcome is Outcome.LOSS
    assert trade.ambiguous is True
    assert trade.r_multiple == pytest.approx(-1.0)
    assert trade.exit_price == pytest.approx(102.0)  # assumed stop first


# --------------------------------------------------------------------------- #
# NO_FILL
# --------------------------------------------------------------------------- #


def test_no_fill(make_ohlc):
    # Bearish entry @100 but price never trades up to 100 after the entry bar.
    bars = [
        (95.0, 96.0, 94.0, 95.5),      # 0
        (95.0, 96.0, 94.0, 95.5),      # 1
        (95.0, 96.0, 94.0, 95.5),      # 2  entry.index
        (95.0, 98.0, 94.0, 95.0),      # 3  high 98 < 100
        (95.0, 97.0, 90.0, 91.0),      # 4  drifts away, never reaches 100
    ]
    df = make_ohlc(bars)
    trade = simulate_entry(_bearish_entry(index=2), df)
    assert trade.outcome is Outcome.NO_FILL
    assert trade.filled is False
    assert trade.fill_index is None
    assert trade.r_multiple == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# TIMEOUT (max_hold)
# --------------------------------------------------------------------------- #


def test_timeout_exits_at_close(make_ohlc):
    # Fill on bar 3, then chop without hitting SL/TP; max_hold=1 -> exit at the
    # close of bar 4 (one bar after the fill).
    bars = [
        (95.0, 96.0, 94.0, 95.5),      # 0
        (95.0, 96.0, 94.0, 95.5),      # 1
        (95.0, 96.0, 94.0, 95.5),      # 2  entry.index
        (97.0, 100.5, 96.5, 99.0),     # 3  FILL (high 100.5)
        (99.0, 99.8, 97.5, 98.0),      # 4  no SL(102)/TP(96); close 98.0
        (98.0, 99.0, 95.0, 95.5),      # 5  would TP but we've timed out already
    ]
    df = make_ohlc(bars)
    trade = simulate_entry(_bearish_entry(index=2), df, max_hold=1)
    assert trade.outcome is Outcome.TIMEOUT
    assert trade.exit_index == 4
    assert trade.exit_price == pytest.approx(98.0)
    # Bearish: moved from 100 down to 98 -> +1.0 R (2-point favourable / 2 risk).
    assert trade.r_multiple == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Aggregate result statistics + equity curve
# --------------------------------------------------------------------------- #


def _win_bars():
    return [
        (95.0, 96.0, 94.0, 95.5),
        (95.0, 96.0, 94.0, 95.5),
        (95.0, 96.0, 94.0, 95.5),
        (97.0, 100.5, 96.5, 99.0),    # fill
        (99.0, 99.5, 95.5, 96.5),     # TP
    ]


def _loss_bars():
    return [
        (95.0, 96.0, 94.0, 95.5),
        (95.0, 96.0, 94.0, 95.5),
        (95.0, 96.0, 94.0, 95.5),
        (97.0, 100.5, 96.5, 99.5),    # fill
        (99.5, 102.5, 99.0, 101.5),   # stop
    ]


def test_aggregate_two_wins_one_loss(make_ohlc):
    df_win = make_ohlc(_win_bars())
    df_loss = make_ohlc(_loss_bars())

    win1 = simulate_entry(_bearish_entry(index=2), df_win)
    loss = simulate_entry(_bearish_entry(index=2), df_loss)
    win2 = simulate_entry(_bearish_entry(index=2), df_win)

    result = BacktestResult(trades=[win1, loss, win2])

    assert result.num_trades == 3
    assert result.wins == 2
    assert result.losses == 1
    assert result.win_rate == pytest.approx(2 / 3)
    # Total R = +2 -1 +2 = 3 ; expectancy = 1.0
    assert result.total_r == pytest.approx(3.0)
    assert result.expectancy == pytest.approx(1.0)
    assert result.average_rr == pytest.approx(2.0)  # all planned 1:2
    # Profit factor = gross profit (4) / gross loss (1) = 4
    assert result.profit_factor == pytest.approx(4.0)
    assert result.max_consecutive_losses == 1
    # Equity curve runs +2 -> +1 -> +3
    curve = result.equity_curve
    assert list(curve) == pytest.approx([2.0, 1.0, 3.0])
    # Summary renders without error and includes headline numbers.
    text = result.summary()
    assert "win rate" in text
    assert "expectancy" in text


def test_run_backtest_with_no_fill_excluded(make_ohlc):
    # One win and one no-fill -> only the win counts towards stats / equity.
    df = make_ohlc(_win_bars())
    no_fill_df = make_ohlc(
        [
            (95.0, 96.0, 94.0, 95.5),
            (95.0, 96.0, 94.0, 95.5),
            (95.0, 96.0, 94.0, 95.5),
            (95.0, 98.0, 94.0, 95.0),  # never reaches 100
        ]
    )
    win = simulate_entry(_bearish_entry(index=2), df)
    nf = simulate_entry(_bearish_entry(index=2), no_fill_df)
    result = BacktestResult(trades=[win, nf])
    assert result.num_signals == 2
    assert result.num_trades == 1
    assert result.no_fills == 1
    assert result.total_r == pytest.approx(2.0)
    assert len(result.equity_curve) == 1


def test_run_backtest_engine(make_ohlc):
    # run_backtest over a list with shared df; bearish wins.
    df = make_ohlc(_win_bars())
    entries = [_bearish_entry(index=2)]
    result = run_backtest(entries, df)
    assert result.num_trades == 1
    assert result.wins == 1


def test_risk_per_trade_scales_r(make_ohlc):
    df = make_ohlc(_win_bars())
    result = run_backtest([_bearish_entry(index=2)], df, risk_per_trade=0.5)
    # +2R win scaled by 0.5 -> +1.0
    assert result.total_r == pytest.approx(1.0)


def test_max_consecutive_losses(make_ohlc):
    df_loss = make_ohlc(_loss_bars())
    df_win = make_ohlc(_win_bars())
    l = lambda: simulate_entry(_bearish_entry(index=2), df_loss)
    w = lambda: simulate_entry(_bearish_entry(index=2), df_win)
    result = BacktestResult(trades=[l(), l(), w(), l(), l(), l()])
    assert result.max_consecutive_losses == 3


# --------------------------------------------------------------------------- #
# Empty result edge cases
# --------------------------------------------------------------------------- #


def test_empty_result():
    result = BacktestResult(trades=[])
    assert result.num_trades == 0
    assert result.win_rate == 0.0
    assert result.expectancy == 0.0
    assert result.profit_factor == 0.0
    assert list(result.equity_curve) == []
    assert isinstance(result.summary(), str)


# --------------------------------------------------------------------------- #
# End-to-end on real data (guarded)
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    not DEFAULT_DATA_DIR.exists(), reason="raw MMC data directory not present"
)
def test_backtest_symbol_smoke():
    # Small bar limit keeps it fast; we only assert it runs and returns sane types.
    result = backtest_symbol(
        "EURUSD", Timeframe.H1, entry_type="sharp_turn", rr=2.0, limit=400
    )
    assert isinstance(result, BacktestResult)
    assert result.num_signals >= 0
    assert 0.0 <= result.win_rate <= 1.0
    # Equity curve length matches the number of filled trades.
    assert len(result.equity_curve) == result.num_trades
    assert isinstance(result.summary(), str)

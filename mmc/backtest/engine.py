"""The backtest engine — wires :class:`~mmc.entry.Entry` signals through the
fill model into an aggregate :class:`~mmc.backtest.result.BacktestResult`.

``run_backtest`` is the low-level entry point (you bring your own entries +
DataFrame). ``backtest_symbol`` is the convenience wrapper that runs the whole
MMC stack end-to-end: ``mmc.data.load`` -> ``mmc.context.find_context_areas`` ->
``mmc.entry.find_entries`` -> the engine.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

import pandas as pd

from mmc.context import find_context_areas
from mmc.core.types import Timeframe
from mmc.data import load
from mmc.entry import Entry, find_entries

from .fill import simulate_entry
from .result import BacktestResult, Trade


def run_backtest(
    entries: Sequence[Entry],
    df: pd.DataFrame,
    *,
    max_hold: Optional[int] = None,
    risk_per_trade: float = 1.0,
) -> BacktestResult:
    """Fill and resolve every ``entry`` against ``df``; aggregate the trades.

    Parameters
    ----------
    entries:
        The entry signals to simulate. Order is preserved (the equity curve is
        built in this order). Entries are assumed to belong to ``df``.
    df:
        The entry-timeframe OHLC DataFrame the entries were generated on.
    max_hold:
        Optional max bars to hold after the fill bar before a timeout exit.
    risk_per_trade:
        Scales every trade's R-multiple (i.e. fixed-fractional sizing in R).
        Defaults to ``1.0`` so the result is reported in clean ``R`` units; pass
        e.g. ``0.5`` to risk half an R per trade.
    """
    trades: List[Trade] = []
    for entry in entries:
        trade = simulate_entry(entry, df, max_hold=max_hold)
        if risk_per_trade != 1.0:
            trade.r_multiple *= risk_per_trade
        trades.append(trade)
    return BacktestResult(trades=trades)


def backtest_symbol(
    symbol: str,
    timeframe: Timeframe,
    *,
    context_tf: Optional[Timeframe] = None,
    entry_type: str = "sharp_turn",
    killzone: Optional[str] = None,
    rr: float = 2.0,
    max_hold: Optional[int] = None,
    risk_per_trade: float = 1.0,
    limit: Optional[int] = None,
    data_dir=None,
) -> BacktestResult:
    """End-to-end backtest for one ``symbol`` on its ``timeframe``.

    Pipeline (transcript 10 -> 11 -> backtest):

    1. ``mmc.data.load`` the entry-timeframe bars (and a higher ``context_tf`` if
       one is given, else context is derived on the same timeframe).
    2. ``mmc.context.find_context_areas`` on the context DataFrame.
    3. ``mmc.entry.find_entries`` inside every context area on the entry bars.
    4. ``run_backtest`` over all entries.

    ``limit`` caps the number of *entry-timeframe* bars loaded (from the start)
    to keep large datasets fast. ``context_tf`` defaults to ``timeframe`` so the
    helper is usable with a single timeframe; supply a higher one (e.g. D1
    context with H1 entries) for a realistic top-down run.
    """
    entry_df = load(symbol, timeframe, data_dir=data_dir)
    if limit is not None:
        entry_df = entry_df.iloc[:limit]

    if context_tf is None or context_tf == timeframe:
        context_df = entry_df
    else:
        context_df = load(symbol, context_tf, data_dir=data_dir)

    context_areas = find_context_areas(context_df)

    entries: List[Entry] = []
    for ctx in context_areas:
        entries.extend(
            find_entries(ctx, entry_df, entry_type=entry_type, killzone=killzone, rr=rr)
        )

    # Keep deterministic, chronological order for the equity curve.
    entries.sort(key=lambda e: e.index)

    return run_backtest(
        entries, entry_df, max_hold=max_hold, risk_per_trade=risk_per_trade
    )

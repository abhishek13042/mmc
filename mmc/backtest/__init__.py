"""MMC backtest layer — a deterministic, event-driven trade simulator.

This is the "library first, **then backtest**" deliverable: it sits entirely on
top of the :class:`~mmc.entry.Entry` signals and the OHLC DataFrames produced by
``mmc.data``, and never re-derives FVGs / swings / lags / context.

Modelling in one sentence: a resting **limit order** at the entry FVG edge fills
when price trades into the zone, then resolves to a **stop loss** (against) or a
**take profit** (1:2 RR by default), bar by bar, with ambiguous same-bar
SL/TP bars resolved conservatively as losses — everything reported in
instrument-agnostic **R-multiples** (``R = |entry - stop|``).

Public API
----------
``Outcome``
    The WIN / LOSS / TIMEOUT / NO_FILL enum.
``Trade``
    A single simulated trade (fill, exit, realised R, ambiguity flag).
``BacktestResult``
    Aggregated stats (win rate, expectancy, average RR, profit factor,
    max consecutive losses, equity curve) + ``.summary()``.
``simulate_entry(entry, df, *, max_hold=None)``
    The fill model for one entry.
``run_backtest(entries, df, *, max_hold=None, risk_per_trade=1.0)``
    Run the engine over a list of entries.
``backtest_symbol(symbol, timeframe, *, context_tf=..., entry_type=..., rr=2.0, limit=None)``
    End-to-end: data -> context -> entries -> engine.
"""

from .engine import backtest_symbol, run_backtest
from .fill import simulate_entry
from .result import BacktestResult, Outcome, Trade

__all__ = [
    "Outcome",
    "Trade",
    "BacktestResult",
    "simulate_entry",
    "run_backtest",
    "backtest_symbol",
]

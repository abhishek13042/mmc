"""Strategy evaluation & qualification pipeline.

Turns a per-trade log (one row per filled trade, R-multiples — see
:mod:`mmc.evaluation.schema`) into the full "is this edge real and fundable?"
stack rather than the four vanity numbers (WR / PF / ExpR / total-R) the console
backtests print today:

  * statistical validity  — Wilson CI on win rate, bootstrap PF/ExpR bands
  * core                  — WR, PF, expectancy, payoff ratio  (formula parity
                            with :class:`mmc.backtest.result.BacktestResult`)
  * drawdown / risk       — max DD (R & %), DD duration, longest losing streak,
                            recovery factor, Ulcer index
  * risk-adjusted         — Sortino, Calmar (Sharpe for reference)
  * stability             — per-quarter WR/PF buckets, skew, kurtosis
  * robustness            — in-sample vs out-of-sample decay, Monte Carlo shuffle
  * portfolio             — cross-strategy correlation, true-timing combined
                            equity, peak concurrent open-risk

then applies pre-committed pass/fail thresholds (:mod:`mmc.evaluation.qualify`)
and writes CSV + Markdown + PNG reports (:mod:`mmc.evaluation.report`).

Entry point:  ``python -m mmc.evaluation --trades <trades.csv>``
"""

from mmc.evaluation.schema import TRADE_COLUMNS, load_trades
from mmc.evaluation.config import QualifyConfig
from mmc.evaluation.qualify import qualify_strategy, Qualification

__all__ = [
    "TRADE_COLUMNS",
    "load_trades",
    "QualifyConfig",
    "qualify_strategy",
    "Qualification",
]

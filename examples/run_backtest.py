"""Run an MMC backtest end-to-end on the raw data.

Usage:
    python examples/run_backtest.py [SYMBOL] [TIMEFRAME] [LIMIT]

Examples:
    python examples/run_backtest.py
    python examples/run_backtest.py XAUUSD H1 3000
    python examples/run_backtest.py GBPUSD H4
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running directly (`python examples/run_backtest.py`) without installing.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mmc.backtest import backtest_symbol  # noqa: E402
from mmc.core.types import Timeframe  # noqa: E402


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "EURUSD"
    tf = Timeframe[sys.argv[2]] if len(sys.argv) > 2 else Timeframe.H1
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 2000

    print(f"Backtesting {symbol} {tf.name} (last {limit} bars)...\n")
    result = backtest_symbol(symbol, tf, limit=limit)
    print(result.summary())


if __name__ == "__main__":
    main()

"""Load the raw MMC market-data CSVs into pandas DataFrames.

Raw files live under ``mmc_backtest/data/raw`` and are **tab-separated with no
header**. Columns are: datetime, open, high, low, close, volume. The numeric
suffix in the filename is the timeframe in minutes (``EURUSD60.csv`` -> H1).

A loaded DataFrame is the canonical OHLC structure used everywhere in the
library: a ``DatetimeIndex`` (sorted ascending) and float columns
``open, high, low, close, volume``. Detectors address bars by **integer
position** (``df.iloc`` position), so the index is always reset to be
contiguous 0..n-1 in positional terms via ``df.reset_index`` only when needed by
callers — the DataFrame itself keeps its DatetimeIndex.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

import pandas as pd

from ..core.types import Timeframe

# .../mmc/data/loader.py -> parents[2] == project root (D:/MMC)
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "mmc_backtest" / "data" / "raw"

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]

_FILENAME_RE = re.compile(r"^([A-Za-z]+)(\d+)$")


def _resolve_dir(data_dir: Path | str | None) -> Path:
    return Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR


def load(
    symbol: str,
    timeframe: Timeframe,
    data_dir: Path | str | None = None,
) -> pd.DataFrame:
    """Load one ``symbol``/``timeframe`` into an OHLCV DataFrame.

    Raises ``FileNotFoundError`` if the CSV is missing.
    """
    directory = _resolve_dir(data_dir)
    path = directory / f"{symbol.upper()}{timeframe.file_code}.csv"
    if not path.exists():
        raise FileNotFoundError(f"No data file for {symbol} {timeframe.name}: {path}")

    df = pd.read_csv(
        path,
        sep="\t",
        header=None,
        names=["datetime", *OHLCV_COLUMNS],
        parse_dates=["datetime"],
    )
    df = df.set_index("datetime").sort_index()
    # Enforce numeric dtypes (defensive against stray rows).
    df[OHLCV_COLUMNS] = df[OHLCV_COLUMNS].astype(float)
    df.attrs["symbol"] = symbol.upper()
    df.attrs["timeframe"] = timeframe
    return df


def load_all_timeframes(
    symbol: str,
    data_dir: Path | str | None = None,
) -> Dict[Timeframe, pd.DataFrame]:
    """Load every available timeframe for a symbol, keyed by :class:`Timeframe`."""
    out: Dict[Timeframe, pd.DataFrame] = {}
    for tf in Timeframe:
        try:
            out[tf] = load(symbol, tf, data_dir=data_dir)
        except FileNotFoundError:
            continue
    if not out:
        raise FileNotFoundError(f"No data files found for symbol {symbol!r}")
    return out


def available_symbols(data_dir: Path | str | None = None) -> List[str]:
    """Return the distinct symbols present in the data directory (sorted)."""
    directory = _resolve_dir(data_dir)
    symbols = set()
    for p in directory.glob("*.csv"):
        m = _FILENAME_RE.match(p.stem)
        if m:
            symbols.add(m.group(1).upper())
    return sorted(symbols)

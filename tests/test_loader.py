"""Tests for the data loader against the real raw CSVs (transcript-agnostic)."""

import pandas as pd
import pytest

from mmc.core.types import Timeframe
from mmc.data import available_symbols, load, load_all_timeframes
from mmc.data.loader import DEFAULT_DATA_DIR

pytestmark = pytest.mark.skipif(
    not DEFAULT_DATA_DIR.exists(), reason="raw data directory not present"
)


def test_available_symbols():
    syms = available_symbols()
    assert "EURUSD" in syms
    assert "GBPUSD" in syms
    assert "XAUUSD" in syms


def test_load_h1():
    df = load("EURUSD", Timeframe.H1)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.is_monotonic_increasing
    assert len(df) > 1000
    assert (df["high"] >= df["low"]).all()
    assert df.attrs["timeframe"] is Timeframe.H1


def test_load_all_timeframes():
    data = load_all_timeframes("XAUUSD")
    assert set(data.keys()) == set(Timeframe)
    for tf, df in data.items():
        assert len(df) > 0


def test_missing_symbol_raises():
    with pytest.raises(FileNotFoundError):
        load("NOPE", Timeframe.H1)

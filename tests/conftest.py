"""Shared pytest fixtures and helpers for the MMC test suite."""

from __future__ import annotations

import pandas as pd
import pytest


def make_df(bars) -> pd.DataFrame:
    """Build an OHLCV DataFrame from a list of (open, high, low, close) or
    (open, high, low, close, volume) tuples with a synthetic minute index."""
    rows = []
    for b in bars:
        if len(b) == 4:
            o, h, l, c = b
            v = 1.0
        else:
            o, h, l, c, v = b
        rows.append((o, h, l, c, v))
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"])
    df.index = pd.date_range("2024-01-01", periods=len(df), freq="1min")
    return df


@pytest.fixture
def make_ohlc():
    return make_df

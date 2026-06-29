"""Volatility profile from data — deriving *when* the market moves (transcript 09).

transcript 09 (~15:18): "go to a website where it shows the average movement of
price for any particular day. And if you look at the days where we have the most
movement, that is also the days where we have the most news events." Time is
volatility, so we can *measure* time directly off the data: bucket bars by
hour-of-day and average their range.

The rule that falls out of it (~6:09, ~15:30): trade the hours whose volatility
is **above the average line** — those are the volatile, higher-probability
hours; the below-average hours tend to consolidate.

These are pure functions over an OHLC DataFrame with a ``DatetimeIndex`` and the
canonical float columns ``open/high/low/close`` (see :mod:`mmc.data`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def bar_range(df: pd.DataFrame) -> pd.Series:
    """Per-bar high-low range, indexed like ``df``."""
    return (df["high"] - df["low"]).astype(float)


def true_range(df: pd.DataFrame) -> pd.Series:
    """Per-bar *true* range (max of H-L, |H-prevClose|, |L-prevClose|).

    The first bar has no previous close, so it falls back to plain H-L.
    """
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    prev_close = df["close"].astype(float).shift(1)
    hl = high - low
    hc = (high - prev_close).abs()
    lc = (low - prev_close).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    tr.iloc[0] = hl.iloc[0]
    return tr.astype(float)


def volatility_by_hour(df: pd.DataFrame, use_true_range: bool = False) -> pd.Series:
    """Average bar range per hour-of-day (0–23) from an OHLC DataFrame.

    Returns a :class:`pandas.Series` indexed by integer hour (name ``"hour"``),
    sorted ascending, holding the mean range of every bar that opened in that
    hour. Hours with no bars are simply absent from the result.

    The hour is read off ``df.index`` as-is (the index timezone defines the
    "time of day"); the loader stores New-York-local timestamps.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("volatility_by_hour requires a DatetimeIndex")
    rng = true_range(df) if use_true_range else bar_range(df)
    hours = pd.Index(df.index.hour, name="hour")
    profile = rng.groupby(hours).mean()
    profile.name = "avg_range"
    return profile.sort_index()


def above_average_hours(profile: pd.Series) -> pd.Series:
    """Boolean mask flagging hours whose avg range is **above the mean line**.

    "Trade when volatility is above average" (transcript 09). The mean line is
    the average of the hourly profile itself. The result is a boolean Series
    aligned to ``profile``'s hour index.
    """
    line = float(profile.mean()) if len(profile) else np.nan
    mask = profile > line
    mask.name = "above_average"
    return mask


def is_volatile_hour(hour: int, profile: pd.Series) -> bool:
    """Is ``hour`` an above-average (volatile) hour for this ``profile``?

    Hours absent from the profile (no data) return ``False``.
    """
    mask = above_average_hours(profile)
    if hour not in mask.index:
        return False
    return bool(mask.loc[hour])

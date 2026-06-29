"""MMC — Money Making Concepts trading framework.

The library is organised in dependency layers (see ARCHITECTURE.md):

    data      -> load OHLC CSVs into pandas (foundation)
    core      -> primitives: swings, fair value gaps, market structure,
                 fair value areas, order flow lags (foundation, transcripts 1-3)
    narrative -> FLOD / ODD / LOD, FVG & FVA quality, sweeps   (transcripts 4,6,7,8)
    candle_science -> respect / disrespect candles             (transcript 5)
    timing    -> time = volatility, news, sessions             (transcript 9)
    context   -> usual / unusual context areas                 (transcript 10)
    entry     -> sharp turns, order flow entries, MM model     (transcript 11)
    topdown   -> filtering-process vs flow trader              (transcript 12)
    backtest  -> trade simulation on top of the library

Foundation (data + core) is the shared contract every higher layer imports.
"""

from . import (
    backtest,
    candle_science,
    context,
    core,
    data,
    entry,
    narrative,
    sweeps,
    timing,
    topdown,
)

__all__ = [
    "core",
    "data",
    "narrative",
    "sweeps",
    "candle_science",
    "timing",
    "context",
    "entry",
    "topdown",
    "backtest",
]
__version__ = "0.1.0"

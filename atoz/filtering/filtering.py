"""Filtering / pair selection (A-Z Guide ep 14).

> SMT alone is not enough to pick which instrument to execute on — find the
> **strength leader** on a higher-timeframe basis and trade that one: for longs
> the instrument that has been moving up *more easily* over recent days, for
> shorts the weaker one. Trade the strong pair in the bias direction.  — ep 13/14

NOTE: this module is implemented from the strength-leader concept referenced in
ep 13 (the SMT video forward-references ep 14 pair selection). Verify against the
ep-14 transcript (file 015) when refining.

We rank correlated instruments by normalised recent return (relative strength)
so the caller trades the leader for longs / the laggard for shorts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import pandas as pd


@dataclass
class StrengthRank:
    symbol: str
    rel_strength: float   # normalised recent return (higher = stronger)


def relative_strength(closes: Dict[str, pd.Series], lookback: int = 20) -> List[StrengthRank]:
    """Rank instruments by normalised recent return over ``lookback`` bars.

    Each series is reduced to (close[-1] / close[-1-lookback] - 1); the result is
    z-scored across instruments so they are comparable regardless of price scale.
    """
    raw: Dict[str, float] = {}
    for sym, s in closes.items():
        if len(s) <= lookback:
            continue
        raw[sym] = float(s.iloc[-1] / s.iloc[-1 - lookback] - 1.0)
    if not raw:
        return []

    vals = list(raw.values())
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    std = var ** 0.5 or 1e-9

    ranks = [StrengthRank(sym, (v - mean) / std) for sym, v in raw.items()]
    ranks.sort(key=lambda r: r.rel_strength, reverse=True)
    return ranks


def select_pair(ranks: List[StrengthRank], direction: str) -> str:
    """Pick the instrument to execute on: the leader for "bullish", the laggard
    for "bearish" (ep 14)."""
    if not ranks:
        raise ValueError("no ranks provided")
    return ranks[0].symbol if direction == "bullish" else ranks[-1].symbol

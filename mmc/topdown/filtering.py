"""Filtering-process orchestration (transcript 12, ~3:38–9:17).

The filtering-process trader scans **many** Forex pairs and uses *arguments* to
pick the single highest-probability pair (~4:04): "from those 10 pairs ... you
will determine that one of those pairs is the highest probability — that's the
one you want to be focussing on." One-sided arguments (all bullish, no bearish)
= highest probability; mixed = ~50/50.

We run a top-down per symbol and rank by probability. The ranking key mirrors the
transcript's priority:

1. **one-sided** beats mixed (the "extremely high probability" regime, ~6:00),
2. then **confidence** (fraction of arguments on the winning side),
3. then the **number of arguments** on the winning side (more arguments for one
   side = stronger, ~9:00 "a lot more arguments for EURUSD to be bullish").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from mmc.core import Direction, Timeframe

from .analysis import TopDownResult, top_down
from .style import TraderStyle


@dataclass
class RankedPair:
    """A symbol's top-down result plus its computed ranking score."""

    symbol: str
    result: TopDownResult
    rank_score: float

    @property
    def direction(self) -> Direction:
        return self.result.direction

    @property
    def one_sided(self) -> bool:
        return self.result.one_sided

    @property
    def confidence(self) -> float:
        return self.result.bias.confidence


def _rank_key(result: TopDownResult):
    """Sort key: one-sided first, then confidence, then winning-side arg count.

    Returns a tuple sorted in *descending* order (higher = stronger).
    """
    bias = result.bias
    winning = max(bias.n_bullish, bias.n_bearish)
    return (1 if bias.one_sided else 0, bias.confidence, winning)


def rank_score(result: TopDownResult) -> float:
    """A single scalar probability score for a top-down result (0..~3).

    Combines the three ranking factors into one number so callers can store /
    compare a single value. one-sided contributes the most, then confidence,
    then a small bump per extra winning argument.
    """
    bias = result.bias
    winning = max(bias.n_bullish, bias.n_bearish)
    return (2.0 if bias.one_sided else 0.0) + bias.confidence + 0.05 * winning


def filter_pairs(
    symbols: List[str],
    style: TraderStyle = TraderStyle.FILTERING_PROCESS,
    data_dir=None,
    bars: Optional[int] = 500,
    window: int = 3,
    data_by_symbol: Optional[Dict[str, Dict[Timeframe, pd.DataFrame]]] = None,
    top_n: Optional[int] = None,
) -> List[RankedPair]:
    """Run the top-down across ``symbols`` and rank them by probability.

    The highest-probability pair is first (transcript 12 filtering process). Each
    symbol's data is loaded via :func:`mmc.data.load_all_timeframes` (honouring a
    small ``bars`` limit for efficiency) unless ``data_by_symbol`` supplies
    ``{symbol: {Timeframe: DataFrame}}`` directly (used by tests for fast,
    deterministic synthetic frames).

    Parameters
    ----------
    symbols
        The instruments to scan.
    bars
        Per-timeframe bar cap (keeps the multi-pair scan efficient). ``None``
        loads everything.
    data_by_symbol
        Optional pre-loaded data, bypassing the loader entirely.
    top_n
        If set, return only the strongest ``top_n`` pairs.

    Returns the list of :class:`RankedPair`, strongest first.
    """
    ranked: List[RankedPair] = []
    for symbol in symbols:
        if data_by_symbol is not None:
            data = data_by_symbol.get(symbol)
            if data is None:
                continue
            result = top_down(data, style=style, bars=bars, window=window)
            result.symbol = symbol
            result.narrative = result.narrative.replace("instrument", symbol, 1)
        else:
            result = top_down(
                symbol,
                style=style,
                data_dir=data_dir,
                bars=bars,
                window=window,
            )
        ranked.append(
            RankedPair(symbol=symbol, result=result, rank_score=rank_score(result))
        )

    ranked.sort(key=lambda rp: _rank_key(rp.result), reverse=True)
    if top_n is not None:
        ranked = ranked[:top_n]
    return ranked


def best_pair(
    symbols: List[str],
    style: TraderStyle = TraderStyle.FILTERING_PROCESS,
    **kwargs,
) -> Optional[RankedPair]:
    """The single highest-probability pair, or ``None`` if ``symbols`` is empty
    (transcript 12, ~4:24 — "that one of those pairs is the highest probability")."""
    ranked = filter_pairs(symbols, style=style, **kwargs)
    return ranked[0] if ranked else None

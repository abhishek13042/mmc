"""MMC top-down layer (transcript 12 — A Top-Down Analysis that suits YOU).

The final layer. A top-down's purpose is **not** entry; it is to find, in order
(transcript 12, ~0:41): **direction → narrative → a high-probability context
area** where we then look for entries. This layer orchestrates every layer below
it to produce that result, in the two styles the transcript describes:

* **Filtering-process trader** — higher timeframe, many Forex pairs, picks the
  single highest-probability pair via *arguments* (order flow + market structure
  + candle science). One-sided arguments = highest probability; mixed = ~50/50.
* **Flow trader** — lower timeframe, one volatile instrument, reactive
  "ping-pong", guided by 15m/1H FVGs toward higher-TF PD arrays.

Public API
----------
Styles (transcript 12, ~1:30 / ~3:38 / ~9:26)
    ``TraderStyle`` / ``StyleConfig`` / ``style_config`` and the presets
    ``FILTERING_PROCESS_CONFIG`` / ``FLOW_CONFIG``.

Bias / arguments engine (transcript 12, ~5:27)
    ``Argument`` / ``Bias`` / ``compute_bias`` — accumulate objective bullish vs
    bearish arguments from order flow, market structure and candle science.

Top-down (transcript 12, ~0:41)
    ``TopDownResult`` / ``top_down`` — run the direction → narrative → context
    chain for one instrument.

Filtering process (transcript 12, ~4:04)
    ``RankedPair`` / ``filter_pairs`` / ``best_pair`` / ``rank_score`` — scan
    many pairs and rank by probability.

Orchestrated layers: ``mmc.core`` (swings/FVGs/lags/structure),
``mmc.candle_science`` (candle direction), ``mmc.context``
(``find_context_areas``) and ``mmc.data`` (loading). Primitives are never
re-derived here.
"""

from __future__ import annotations

from .analysis import TopDownResult, top_down
from .bias import Argument, Bias, compute_bias
from .filtering import RankedPair, best_pair, filter_pairs, rank_score
from .style import (
    FILTERING_PROCESS_CONFIG,
    FLOW_CONFIG,
    HTF_CONTEXT_TIMEFRAMES,
    StyleConfig,
    TraderStyle,
    style_config,
)

__all__ = [
    # styles
    "TraderStyle",
    "StyleConfig",
    "style_config",
    "FILTERING_PROCESS_CONFIG",
    "FLOW_CONFIG",
    "HTF_CONTEXT_TIMEFRAMES",
    # bias / arguments
    "Argument",
    "Bias",
    "compute_bias",
    # top-down
    "TopDownResult",
    "top_down",
    # filtering process
    "RankedPair",
    "filter_pairs",
    "best_pair",
    "rank_score",
]

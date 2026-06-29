"""Candle science (transcript 05).

**Candle science = order flow seen through a single candle on a higher
timeframe.** A daily order flow lag is one candle on the weekly/monthly; the
fewer candles you must predict, the higher your accuracy.

Two candle kinds:

* **Disrespect** — one-sided order flow (only bullish OR only bearish). Bullish
  disrespect = up candle, small wick at the top; bearish = down candle, small
  wick at the bottom. → continue in the candle's direction.
* **Respect** — order flow lags on *both* sides (a reversal inside the candle).
  Bullish respect = long wick at the bottom; bearish respect = long wick at the
  top. → continue in the direction of the respect (away from the long wick).
  Respect candles form at PD arrays.

Public API
----------
Geometry (judge a candle by its own shape)::

    from mmc.candle_science import classify_candle, classify_candles

Fractal (judge a candle by the lower-TF order flow inside it)::

    from mmc.candle_science import classify_from_order_flow, order_flow_lags_in

Direction helper::

    from mmc.candle_science import next_candle_direction

Types::

    from mmc.candle_science import CandleClass, CandleScience
"""

from .classify import (
    DEFAULT_BODY_RATIO_FLOOR,
    DEFAULT_RESPECT_WICK_RATIO,
    classify_candle,
    classify_candles,
    next_candle_direction,
)
from .fractal import classify_from_order_flow, order_flow_lags_in
from .types import CandleClass, CandleScience

__all__ = [
    # types
    "CandleClass",
    "CandleScience",
    # geometric classification
    "classify_candle",
    "classify_candles",
    "DEFAULT_RESPECT_WICK_RATIO",
    "DEFAULT_BODY_RATIO_FLOOR",
    # fractal / order-flow classification
    "classify_from_order_flow",
    "order_flow_lags_in",
    # direction helper
    "next_candle_direction",
]

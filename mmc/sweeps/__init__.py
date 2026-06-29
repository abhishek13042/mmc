"""Liquidity sweeps / turtle soups (transcript 08).

This layer sits on top of ``mmc.core`` and answers a single question: when price
trades beyond a piece of liquidity (a swing point), did it **sweep** it (trade
beyond then aggressively reverse — a turtle soup) or **run** it (trade beyond and
continue)? It also exposes the two fractal lenses on a sweep:

* **Order flow sweep** — an actual swing high/low left behind after a mitigated
  FVG's rejection failed to make a new FVG (the mitigated FVG is dropped).
* **Candle science sweep** — a previous-candle-high / previous-candle-low
  (PCH/PCL) sweep where the first candle into the array does not reject.

Public API
----------
Liquidity classification (``mmc.sweeps.liquidity``)
    LiquidityEvent, LiquidityClassification,
    classify_liquidity, mark_swept_swings, liquidity_sweeps

Candle science (``mmc.sweeps.candle_science``)
    previous_candle_high, previous_candle_low,
    CandleScienceSweep, candle_science_sweeps

Order flow (``mmc.sweeps.order_flow``)
    OrderFlowSweep, order_flow_sweeps
"""

from .candle_science import (
    CandleScienceSweep,
    candle_science_sweeps,
    previous_candle_high,
    previous_candle_low,
)
from .liquidity import (
    LiquidityClassification,
    LiquidityEvent,
    classify_liquidity,
    liquidity_sweeps,
    mark_swept_swings,
)
from .order_flow import OrderFlowSweep, order_flow_sweeps

__all__ = [
    # liquidity sweep vs run
    "LiquidityEvent",
    "LiquidityClassification",
    "classify_liquidity",
    "mark_swept_swings",
    "liquidity_sweeps",
    # candle science (PCH / PCL)
    "previous_candle_high",
    "previous_candle_low",
    "CandleScienceSweep",
    "candle_science_sweeps",
    # order flow sweep
    "OrderFlowSweep",
    "order_flow_sweeps",
]

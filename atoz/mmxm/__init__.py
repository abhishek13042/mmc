"""atoz.mmxm — Market Maker Model (MMXM) + simplified Daily Bias.

Faithful implementation of two A-Z Guide episodes:

* **ep 34** — *All the Market Maker Model Secrets* (transcript 035). The market
  maker buy model (MMBM) and sell model (MMSM): two curves. The *context* is a
  move from a discount array to a premium array (bullish) — or premium→discount
  (bearish) — read on a higher timeframe in "just two candles". The model itself
  is the price action *in between* that discount and premium array on the entry
  timeframe. It starts with an **ST** (a fair value gap that confirms the
  intermediate-term low/high of the model — the *curve turn*), then unfolds as a
  sequence of **short-term ranges** that each must contain a fair value gap and
  that "hold" one after another toward the target (the premium array = the draw
  on liquidity). Reclaimed order blocks form on the first curve.  — ep 34

* **ep 36** — *Best Daily Bias Concept (simplified)* (transcript 037). The daily
  bias is read entirely from fair value gaps. A **lag** (swing-low→swing-high
  impulse leg) with a fair value gap in it is a *strong* lag (high probability);
  without one it is weak. Even a lag *with* an FVG is low-probability if the
  timeframe above it has an opposing FVG just beyond the lag (every timeframe in
  context of the one above). The **draw on liquidity** is the higher-timeframe
  FVG (a magnet). **Respect** (only wicking an FVG) = continuation;
  **disrespect** (closing inside or fully through it) = reversal. Bias is
  bullish / bearish / neutral.  — ep 36

Reuses ``atoz.core`` (Direction, Swing, FVG, find_swings, find_fvgs),
``atoz.blocks`` (reclaimed order blocks form on the first curve) and
``atoz.profiles`` (AMD vocabulary).
"""

from __future__ import annotations

from .model import (
    ModelType,
    Phase,
    Curve,
    ShortTermRange,
    MarketMakerModel,
    find_market_maker_models,
    find_short_term_ranges,
)
from .daily_bias import (
    Bias,
    LagStrength,
    FVGRespect,
    Lag,
    DailyBias,
    classify_lag,
    fvg_respect,
    daily_bias,
    daily_bias_series,
)

__all__ = [
    # ep 34 — Market Maker Model
    "ModelType", "Phase", "Curve", "ShortTermRange", "MarketMakerModel",
    "find_market_maker_models", "find_short_term_ranges",
    # ep 36 — Daily Bias
    "Bias", "LagStrength", "FVGRespect", "Lag", "DailyBias",
    "classify_lag", "fvg_respect", "daily_bias", "daily_bias_series",
]

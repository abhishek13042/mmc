"""Candle-science types (transcript 05 — Candle Science).

Candle science = order flow seen through a single candle on a higher timeframe.
A daily order flow lag is one candle on the weekly/monthly. This module defines
the vocabulary used by the rest of the layer:

* :class:`CandleClass` — disrespect vs respect (the two kinds of candle).
* :class:`CandleScience` — a classified candle: its class, its :class:`Direction`
  (the polarity / the way it tells us price wants to continue) and the geometry
  ratios that produced the label.

The polarity convention matches the rest of the library
(:class:`mmc.core.Direction`):

* **Bullish disrespect** — up candle, small wick at the *top* → continue up.
* **Bearish disrespect** — down candle, small wick at the *bottom* → continue down.
* **Bullish respect** — long wick at the *bottom* (reversal up) → continue up.
* **Bearish respect** — long wick at the *top* (reversal down) → continue down.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mmc.core.types import Direction


class CandleClass(Enum):
    """The two candle kinds of candle science (transcript 05).

    * ``DISRESPECT`` — one-sided order flow (only bullish OR only bearish inside).
      Continue in the candle's own direction.
    * ``RESPECT`` — order flow lags on *both* sides (a reversal inside the
      candle), forming a long wick. Continue *away* from the long wick. Respect
      candles form at PD arrays (the candle wicks a swing / FVG / FVA).
    """

    DISRESPECT = "disrespect"
    RESPECT = "respect"


@dataclass(frozen=True)
class CandleScience:
    """A single candle classified through the lens of candle science.

    ``direction`` is the implied continuation polarity (see module docstring):
    a *bullish* result means the next candle can continue higher, a *bearish*
    result means it can continue lower.

    The ratio fields (all expressed as a fraction of the candle's total range,
    ``high - low``) explain *why* the label was assigned and are handy for
    debugging / threshold tuning:

    * ``body_ratio`` — ``|close - open| / range``
    * ``upper_wick_ratio`` — ``(high - max(open, close)) / range``
    * ``lower_wick_ratio`` — ``(min(open, close) - low) / range``
    """

    candle_class: CandleClass
    direction: Direction
    body_ratio: float
    upper_wick_ratio: float
    lower_wick_ratio: float

    @property
    def is_disrespect(self) -> bool:
        return self.candle_class is CandleClass.DISRESPECT

    @property
    def is_respect(self) -> bool:
        return self.candle_class is CandleClass.RESPECT

    @property
    def is_bullish(self) -> bool:
        return self.direction is Direction.BULLISH

    @property
    def is_bearish(self) -> bool:
        return self.direction is Direction.BEARISH

    @property
    def label(self) -> str:
        """Human label, e.g. ``"bullish disrespect"`` / ``"bearish respect"``."""
        side = "bullish" if self.is_bullish else "bearish"
        return f"{side} {self.candle_class.value}"

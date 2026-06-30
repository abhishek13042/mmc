"""Shared primitives for the A-Z Guide library (self-contained, separate from mmc).

Faithful to the raw A-Z Guide transcripts. A PD array (premium/discount array)
is any zone we trade *from*: premium (sell) when high, discount (buy) when low
(ep 1 — "if I'm looking for lower prices I want a premium array, higher
prices a discount array").

Bars are addressed by integer position (the iloc position in the source
DataFrame), stored as ``index`` on every detected object.

``FVG`` is lazy-re-exported via ``__getattr__`` so that
``from atoz.core.types import FVG`` works without creating a circular import
(``atoz.core.fvg`` imports ``Zone`` from here, so a direct import of
``atoz.core.fvg`` at module load time would be circular).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd


class Direction(Enum):
    """A bullish (discount) or bearish (premium) array / move."""

    BULLISH = "bullish"   # discount array — buy / continue up
    BEARISH = "bearish"   # premium array — sell / continue down

    @property
    def opposite(self) -> "Direction":
        return Direction.BEARISH if self is Direction.BULLISH else Direction.BULLISH

    @property
    def sign(self) -> int:
        return 1 if self is Direction.BULLISH else -1


class SwingType(Enum):
    HIGH = "high"
    LOW = "low"

    @property
    def direction(self) -> Direction:
        # A swing high is a premium (bearish) array; a swing low is discount.
        return Direction.BEARISH if self is SwingType.HIGH else Direction.BULLISH


@dataclass
class Swing:
    """A swing high or low (ep 3/4/10). ``index`` is the bar position."""

    index: int
    price: float
    kind: SwingType
    swept: bool = False

    @property
    def direction(self) -> Direction:
        return self.kind.direction


@dataclass
class Zone:
    """A price band between ``top`` and ``bottom`` at a bar ``index``."""

    top: float
    bottom: float
    index: int
    direction: Direction

    @property
    def midpoint(self) -> float:
        return (self.top + self.bottom) / 2.0

    @property
    def is_premium(self) -> bool:
        return self.direction is Direction.BEARISH

    @property
    def is_discount(self) -> bool:
        return self.direction is Direction.BULLISH

    def contains(self, price: float) -> bool:
        return self.bottom <= price <= self.top

    def overlaps_zone(self, other: "Zone") -> bool:
        return self.bottom <= other.top and self.top >= other.bottom


# --------------------------------------------------------------------------- #
# Candle access helpers — OHLC as numpy for fast positional logic
# --------------------------------------------------------------------------- #


@dataclass
class Candles:
    """Numpy view over an OHLC DataFrame for fast positional candle logic."""

    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    n: int

    @classmethod
    def of(cls, df: pd.DataFrame) -> "Candles":
        return cls(
            open=df["open"].to_numpy(dtype=float),
            high=df["high"].to_numpy(dtype=float),
            low=df["low"].to_numpy(dtype=float),
            close=df["close"].to_numpy(dtype=float),
            n=len(df),
        )

    def is_up(self, i: int) -> bool:
        return self.close[i] > self.open[i]

    def is_down(self, i: int) -> bool:
        return self.close[i] < self.open[i]

    def body_top(self, i: int) -> float:
        return max(self.open[i], self.close[i])

    def body_bottom(self, i: int) -> float:
        return min(self.open[i], self.close[i])


def __getattr__(name: str):
    """Lazy re-export of FVG (defined in atoz.core.fvg, which imports from here).

    ``from atoz.core.types import FVG`` works without a circular import by
    deferring the fvg import to first access time, after both modules are
    fully loaded.
    """
    if name == "FVG":
        from atoz.core.fvg import FVG  # noqa: PLC0415
        return FVG
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Direction", "SwingType", "Swing", "Zone", "Candles", "FVG",
]

"""Core data types shared across the whole MMC library.

These are the *contract*: every higher layer (narrative, context, entry, ...)
imports these classes rather than re-defining its own. Do not duplicate them.

Concept references point at the transcripts under ``transcripts/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Direction(Enum):
    """Polarity of a price move or PD array.

    A *bullish* array is a **discount** array (we look to buy / continue up from it).
    A *bearish* array is a **premium** array (we look to sell / continue down from it).
    (transcript 01 — PD Arrays)
    """

    BULLISH = 1
    BEARISH = -1

    @property
    def opposite(self) -> "Direction":
        return Direction.BEARISH if self is Direction.BULLISH else Direction.BULLISH

    @property
    def sign(self) -> int:
        return self.value


class Timeframe(Enum):
    """Supported timeframes. ``value`` is the bar size in minutes and matches the
    numeric code used in the raw CSV filenames (e.g. ``EURUSD60.csv`` -> H1)."""

    M5 = 5
    M15 = 15
    H1 = 60
    H4 = 240
    D1 = 1440

    @property
    def minutes(self) -> int:
        return self.value

    @property
    def file_code(self) -> str:
        return str(self.value)

    @classmethod
    def from_code(cls, code) -> "Timeframe":
        return cls(int(code))

    def __lt__(self, other: "Timeframe") -> bool:  # allows sorting low -> high
        return self.value < other.value


class SwingType(Enum):
    """A swing high is a premium array (sell-side liquidity sits above it);
    a swing low is a discount array (buy-side liquidity sits below it).
    (transcript 01 — swing points / liquidity)"""

    HIGH = "high"
    LOW = "low"

    @property
    def direction(self) -> Direction:
        # A swing high behaves as a bearish (premium) PD array, and vice-versa.
        return Direction.BEARISH if self is SwingType.HIGH else Direction.BULLISH


@dataclass
class Zone:
    """A price zone anchored to a confirming bar index.

    ``top``/``bottom`` are absolute prices (top >= bottom). ``index`` is the
    integer positional index (``df.iloc`` position) of the bar that confirms the
    object. ``direction`` is the array's polarity (see :class:`Direction`).
    """

    top: float
    bottom: float
    index: int
    direction: Direction

    def __post_init__(self) -> None:
        if self.top < self.bottom:
            self.top, self.bottom = self.bottom, self.top

    @property
    def size(self) -> float:
        return self.top - self.bottom

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


@dataclass
class FairValueGap(Zone):
    """A 3-candle Fair Value Gap (transcript 01 / transcript 06).

    Bullish FVG: candle 2 closes above candle 1's high and candle 3's low stays
    above candle 1's high -> gap = [candle1.high, candle3.low].
    Bearish FVG is the mirror image.

    ``c2_index`` is the *expansion-phase* candle. ``mitigated`` is set once price
    trades back into the gap (an FVG can only be traded into **once**).
    """

    c1_index: int = -1
    c2_index: int = -1  # expansion-phase candle
    c3_index: int = -1
    mitigated: bool = False
    mitigation_index: Optional[int] = None
    # Quality label assigned by the narrative layer (transcript 06):
    # "rejection" | "perfect" | "breakaway" | None
    quality: Optional[str] = None


@dataclass
class SwingPoint:
    """A confirmed swing high/low (transcript 01).

    ``index`` is the middle candle; a swing is only confirmed once the right
    candle closes. ``swept`` is set by the sweeps layer (transcript 08)."""

    index: int
    price: float
    kind: SwingType
    swept: bool = False
    sweep_index: Optional[int] = None

    @property
    def direction(self) -> Direction:
        return self.kind.direction

    @property
    def is_high(self) -> bool:
        return self.kind is SwingType.HIGH

    @property
    def is_low(self) -> bool:
        return self.kind is SwingType.LOW

    @property
    def is_premium(self) -> bool:
        return self.kind is SwingType.HIGH


class StructurePointType(Enum):
    """Market-structure classification of a swing (transcript 02 / 03)."""

    ITH = "intermediate_term_high"
    ITL = "intermediate_term_low"
    STH = "short_term_high"
    STL = "short_term_low"


@dataclass
class StructurePoint:
    """An intermediate- or short-term high/low built on top of a swing.

    ITH = swing high with a lower swing high to its left and right.
    STH = swing high *followed by an FVG* (transcript 02 / 03)."""

    swing: SwingPoint
    kind: StructurePointType
    fvg: Optional[FairValueGap] = None  # set for STH/STL

    @property
    def index(self) -> int:
        return self.swing.index

    @property
    def price(self) -> float:
        return self.swing.price

    @property
    def is_high(self) -> bool:
        return self.kind in (StructurePointType.ITH, StructurePointType.STH)


@dataclass
class FairValueArea(Zone):
    """A Fair Value Area: the zone left by a three-swing movement, spanning from
    an intermediate/short-term high to the opposing low (transcript 02 / 07).

    ``start`` and ``end`` are the two structure points that bound the area."""

    start: Optional[StructurePoint] = None  # e.g. the ITH (for a bearish FVA)
    end: Optional[StructurePoint] = None    # e.g. the ITL
    overlapping_fvg: Optional[FairValueGap] = None  # transcript 07
    nested: Optional["FairValueArea"] = None        # transcript 07
    # Quality label from the narrative layer: "ideal" | "good" | "swept" | None
    quality: Optional[str] = None


@dataclass
class OrderFlowLag:
    """The central object of MMC: a swing point + an FVG (+ the FVA it leaves).

    No FVG -> no order flow lag (transcript 03). The three defenses
    (transcript 04) are populated by the narrative layer:

      * ``flod`` First Line Of Defense  (ideally the FVG)
      * ``odd``  Overlapping Defense     (ideally the FVA)
      * ``lod``  Last Line Of Defense    (the swing point)
    """

    direction: Direction
    swing: SwingPoint
    fvg: FairValueGap
    fva: Optional[FairValueArea] = None
    flod: Optional[Zone] = None
    odd: Optional[Zone] = None
    lod: Optional[SwingPoint] = None

    @property
    def index(self) -> int:
        """Index at which the lag is confirmed (its FVG's 3rd candle)."""
        return self.fvg.c3_index

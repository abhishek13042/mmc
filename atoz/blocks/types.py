"""The PD-array block types (A-Z Guide ep 1-5).

Every block is a price zone we trade *from*, with a **mean threshold** (50% of
the bodies — ep 1) that "ideally shouldn't get disrespected" (an early-warning
level, not a hard invalidation — ep 3).

The five block types and their defining pattern:

    OrderBlock      ep 1 (002) — down/up candle run; high/low broken (displacement)
    MitigationBlock ep 2 (003) — Swing Failure Pattern (a swing fails to take prior)
    BreakerBlock    ep 3 (004) — Breaker Pattern (takes BOTH a swing high and low)
    RejectionBlock  ep 4 (005) — long wick; body swept but not the wick
    ReclaimedOB     ep 5 (006) — an order block traded *through*, now held from the
                                  other side (market-maker two-curve model)

Cross-cutting rule (ep 2-5): a block is strongest when **overlapping** with
other PD arrays. ``overlaps`` counts how many other arrays sit on the zone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List

from atoz.core.types import Direction, Zone


class BlockType(Enum):
    ORDER = "order_block"
    MITIGATION = "mitigation_block"
    BREAKER = "breaker_block"
    REJECTION = "rejection_block"
    RECLAIMED = "reclaimed_order_block"


@dataclass
class PDArray(Zone):
    """A block — a premium/discount array we trade from.

    Inherits ``top, bottom, index, direction`` from :class:`Zone`.

    ``block_type``     which of the five A-Z blocks this is.
    ``mean_threshold`` 50% of the candle bodies (ep 2); the early-warning level.
    ``formed_index``   bar at which the pattern is confirmed (displacement /
                       break). Detection never uses bars after this — no
                       look-ahead.
    ``overlaps``       count of *other* PD arrays overlapping this zone (ep 6 —
                       overlapping = high probability). 0 until marked.
    ``confluence``     names of the overlapping array types (for inspection).
    """

    block_type: BlockType = BlockType.ORDER
    mean_threshold: float = 0.0
    formed_index: int = 0
    overlaps: int = 0
    confluence: List[str] = field(default_factory=list)

    @property
    def is_bullish(self) -> bool:
        return self.direction is Direction.BULLISH

    def mean_threshold_respected(self, close_price: float) -> bool:
        """Per ep 2/4: bullish block holds while close stays above MT; bearish
        while close stays below MT."""
        if self.is_bullish:
            return close_price >= self.mean_threshold
        return close_price <= self.mean_threshold

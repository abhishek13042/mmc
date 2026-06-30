"""A-Z Guide block layer (ep 1-5) — the five PD-array blocks.

    find_order_blocks            ep 1 (transcript 002)
    find_mitigation_blocks       ep 2 (transcript 003)
    find_breaker_blocks          ep 3 (transcript 004)
    find_rejection_blocks        ep 4 (transcript 005)
    find_reclaimed_order_blocks  ep 5 (transcript 006)
    mark_overlaps / strongest    cross-cutting rule mentioned in ep 2-5
                                 ("strongest when overlapping another PD array")

Note: ep 6 (transcript 007) is Liquidity Pools — a separate package (atoz.liquidity).

``find_all_blocks(df)`` runs every detector, marks overlaps against each other
and the FVGs, and returns all blocks sorted by index.
"""

from __future__ import annotations

from typing import List

import pandas as pd

from atoz.core.fvg import find_fvgs
from atoz.core.swings import find_swings

from .breaker_block import find_breaker_blocks
from .mitigation_block import find_mitigation_blocks
from .order_block import find_order_blocks
from .overlap import mark_overlaps, strongest
from .reclaimed_order_block import find_reclaimed_order_blocks
from .rejection_block import find_rejection_blocks
from .types import BlockType, PDArray

__all__ = [
    "PDArray", "BlockType",
    "find_order_blocks", "find_mitigation_blocks", "find_breaker_blocks",
    "find_rejection_blocks", "find_reclaimed_order_blocks",
    "mark_overlaps", "strongest", "find_all_blocks",
]


def find_all_blocks(df: pd.DataFrame, mark: bool = True) -> List[PDArray]:
    """Run all five block detectors, mark overlap confluence, return sorted."""
    swings = find_swings(df)
    fvgs = find_fvgs(df)

    order = find_order_blocks(df)
    blocks: List[PDArray] = (
        order
        + find_mitigation_blocks(df, swings)
        + find_breaker_blocks(df, swings)
        + find_rejection_blocks(df)
        + find_reclaimed_order_blocks(df, order)
    )
    if mark:
        mark_overlaps(blocks, fvgs)
    blocks.sort(key=lambda b: b.index)
    return blocks

"""Overlapping PD-array strength (the rule that runs through ep 3-6).

> PD arrays are strongest when **overlapping** another PD array. Two or three
> discount arrays at the same spot = double / triple the probability. The whole
> skill is finding *where* the most arrays overlap, not drawing a thousand
> lines.  — ep 3 / ep 6

``mark_overlaps`` sets ``overlaps`` (count) and ``confluence`` (the overlapping
block types) on each block by comparing its zone against every other block and,
optionally, fair value gaps.
"""

from __future__ import annotations

from typing import List, Optional

from atoz.core.fvg import FVG

from .types import PDArray


def mark_overlaps(
    blocks: List[PDArray],
    fvgs: Optional[List[FVG]] = None,
    proximity: int = 50,
) -> List[PDArray]:
    """Count, for each block, how many other PD arrays overlap its price zone.

    Only arrays within ``proximity`` bars are considered (a block far away in
    time is not "the same spot"). Mutates and returns ``blocks``.
    """
    fvgs = fvgs or []
    for b in blocks:
        count = 0
        names: List[str] = []
        for other in blocks:
            if other is b:
                continue
            if abs(other.index - b.index) > proximity:
                continue
            if b.overlaps_zone(other):
                count += 1
                names.append(other.block_type.value)
        for f in fvgs:
            if abs(f.index - b.index) > proximity:
                continue
            if b.bottom <= f.top and b.top >= f.bottom:
                count += 1
                names.append("fair_value_gap")
        b.overlaps = count
        b.confluence = names
    return blocks


def strongest(blocks: List[PDArray], min_overlaps: int = 1) -> List[PDArray]:
    """Return only blocks with at least ``min_overlaps`` overlapping arrays,
    sorted by overlap count (most confluent first) — the ep-6 filter against
    "a thousand lines"."""
    qualifying = [b for b in blocks if b.overlaps >= min_overlaps]
    qualifying.sort(key=lambda b: b.overlaps, reverse=True)
    return qualifying


# Alias: score_overlap is a common alternative name for mark_overlaps.
score_overlap = mark_overlaps

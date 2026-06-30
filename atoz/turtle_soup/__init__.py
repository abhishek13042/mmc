"""A-Z Guide turtle-soup & market-structure-secrets layer.

Two transcripts:

* **ep 28** — *Full Trading Plans using Turtle Soups* (``turtle_soup.py``):
  a turtle soup is a liquidity-sweep reversal. Two complete plans:
  seek-and-destroy (range → quadrants → judas sweep → ST model → close target)
  and trending (anticipated sweep into HTF PD array; buying-on-strength /
  selling-on-weakness). Produces ``TurtleSoupTrade`` objects
  (direction, entry, stop, target).

* **ep 32** — *Secrets to Market Structure* (``structure_secrets.py``):
  refinements to reading structure — ITH/ITL as outsiders, the short-term-range
  FVG criterion for a confirmed STH/STL, the "ITH forms only after an ITL is
  taken" rule, protected / last-line-of-defense highs, the intermediate-term
  range, and multi-timeframe projection (HTF short-term = LTF intermediate-term).
"""

from .structure_secrets import (
    IntermediateRange,
    ProjectedStructure,
    SwingTier,
    TieredSwing,
    intermediate_highs,
    intermediate_lows,
    intermediate_ranges,
    is_disrespected,
    mark_protected,
    project_htf_structure,
    short_term_highs,
    short_term_lows,
    tier_swings,
)
from .turtle_soup import (
    Quadrant,
    Range,
    TurtleSoupPlan,
    TurtleSoupTrade,
    find_range,
    find_seek_and_destroy,
    find_strength_weakness,
    find_turtle_soups,
)

__all__ = [
    # ep 28 — turtle soups
    "Quadrant", "Range", "TurtleSoupPlan", "TurtleSoupTrade",
    "find_range", "find_seek_and_destroy", "find_strength_weakness",
    "find_turtle_soups",
    # ep 32 — structure secrets
    "SwingTier", "TieredSwing", "IntermediateRange", "ProjectedStructure",
    "tier_swings", "short_term_highs", "short_term_lows",
    "intermediate_highs", "intermediate_lows", "intermediate_ranges",
    "mark_protected", "is_disrespected", "project_htf_structure",
]

"""atoz.fvg_story — FVG "secret story": Sweep-vs-Run + Consolidation detection.

Faithful implementation of two A-Z Guide episodes:

* **ep 24** — *"Fair Value Gaps tell a Secret Story (Sweep or Run)"*
  After price takes a high/low, the fair value gap *overlapping with that level*
  tells you whether the move is a **sweep** (the FVG is disrespected / fully
  rebalanced → an ST model forms → reversal toward opposing liquidity) or a
  **run** (the FVG is respected → continuation / "stumble higher").  See
  :mod:`atoz.fvg_story.sweep_run`.

* **ep 27** — *"Know When Price Will Consolidate (Step-by-Step)"*
  Seek-and-destroy / consolidation detection: take a major liquidity pool, then
  immediately take the opposing side in one expansion; price magnets back to the
  50% (equilibrium) of that range; **confirmed** only once PD arrays stop
  following through; **over** once price displaces out of the range with a fresh
  FVG and PD arrays follow through again.  See
  :mod:`atoz.fvg_story.consolidation`.

These are the *transcript* definitions — note a sibling ``mmc`` package uses a
different sweep/run proxy; this module deliberately does not match it.
"""

from .sweep_run import (
    StoryType,
    OverlapFVG,
    SweepRunSignal,
    overlapping_fvg,
    classify_sweep_or_run,
    sweep_run_signals,
    expect_sting_only,
)
from .consolidation import (
    Phase,
    ExpansionRange,
    ConsolidationZone,
    find_expansion_ranges,
    pd_arrays_following_through,
    displaces_out_of_range,
    find_consolidations,
    consolidation_flags,
)

__all__ = [
    # ep 24 — sweep vs run
    "StoryType",
    "OverlapFVG",
    "SweepRunSignal",
    "overlapping_fvg",
    "classify_sweep_or_run",
    "sweep_run_signals",
    "expect_sting_only",
    # ep 27 — consolidation / seek-and-destroy
    "Phase",
    "ExpansionRange",
    "ConsolidationZone",
    "find_expansion_ranges",
    "pd_arrays_following_through",
    "displaces_out_of_range",
    "find_consolidations",
    "consolidation_flags",
]

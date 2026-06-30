"""atoz.dealing_range — Dealing Ranges & DOL-via-Fibonacci (A-Z Guide ep 20-21).

ep 20 ("know DOL using Fibonacci"): project where price draws on liquidity by
drawing a Fibonacci over the Judas/manipulation leg and reading the negative
extensions (-0.27, -0.62, -1 symmetrical, -1.62, -2 double-symmetrical) — or
standard deviations (-1, -1.5, -2, -2.5, -3) for indices/futures.

ep 21 ("Full Trading Plan using Dealing Ranges"): a dealing range is a range
that took buy-side then sell-side liquidity (or vice versa); classify any price
as premium (>0.5) / discount (<0.5) / equilibrium; build trades toward the
opposing higher-TF PD array (the DOL).

Quick start::

    import atoz.dealing_range as dr
    from atoz.core import find_swings

    sw = find_swings(df)
    ranges = dr.find_dealing_ranges(df, swings=sw)
    r = ranges[-1]
    r.classify(price)            # PriceZone.PREMIUM / DISCOUNT / EQUILIBRIUM

    proj = dr.project_swing(sw[-2], sw[-1], df)   # DOL fib projection
    proj.projections()           # the negative-extension target levels
"""

from .fibonacci import (
    DOL_LEVELS,
    DOL_LEVELS_CORRECTED,
    STD_DEV_LEVELS,
    LEVEL_NAMES,
    AnchorMode,
    FibLevel,
    ProjectionStyle,
    SwingProjection,
    project_swing,
)
from .plan import DealingRangeTrade, build_trades
from .range import (
    DealingRange,
    PriceZone,
    find_dealing_ranges,
)

__all__ = [
    # ep 20 — DOL via Fibonacci
    "project_swing",
    "SwingProjection",
    "FibLevel",
    "AnchorMode",
    "ProjectionStyle",
    "DOL_LEVELS",
    "DOL_LEVELS_CORRECTED",
    "STD_DEV_LEVELS",
    "LEVEL_NAMES",
    # ep 21 — dealing ranges
    "find_dealing_ranges",
    "DealingRange",
    "PriceZone",
    # ep 21 — trading plan
    "build_trades",
    "DealingRangeTrade",
]

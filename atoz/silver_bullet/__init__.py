"""Silver Bullet & the No-Daily-Bias plan (A-Z Guide ep 31 & ep 33).

Faithful implementations of two transcript episodes:

  * **ep 33 — "trading Silver Bullet (WHEN and WHERE to enter)"**: the swing-rate
    (fib 0 / 0.25 / 0.5 / 0.75 / 1.0) guideline and the explicit *0.75 Silver
    Bullet* mechanic — wait for the 0.75 level, enter the first FVG, target the
    intermediate-term low/high. See ``silver_bullet`` and ``swing_rates``.

  * **ep 31 — "Simple + Effective Trading Plan (No Daily Bias needed)"**: 1H
    intermediate-term structure for direction (no prediction), a killzone bringing
    price into the 1H PD array, then a 1m (two FVGs) / 5m (one FVG) entry pattern.
    See ``no_bias_plan``.

Reuses ``atoz.core`` primitives, ``atoz.timing`` killzones (broker = NY + 7) and
the FVG/swing detectors throughout.
"""

from .swing_rates import (
    SwingRate,
    TermRange,
    find_term_ranges,
)
from .silver_bullet import (
    SILVER_BULLET_WINDOWS_NY,
    SilverBulletSetup,
    find_silver_bullet_setups,
    silver_bullet_window_broker,
)
from .no_bias_plan import (
    EntryPattern,
    NoBiasSetup,
    PLAN_KILLZONES_NY,
    find_no_bias_setups,
)

__all__ = [
    # ep 33 — swing rates
    "SwingRate", "TermRange", "find_term_ranges",
    # ep 33 — Silver Bullet
    "SilverBulletSetup", "find_silver_bullet_setups",
    "SILVER_BULLET_WINDOWS_NY", "silver_bullet_window_broker",
    # ep 31 — No Daily Bias plan
    "EntryPattern", "NoBiasSetup", "find_no_bias_setups", "PLAN_KILLZONES_NY",
]

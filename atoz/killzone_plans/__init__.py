"""Session trading plans (A-Z Guide ep 29 & ep 30).

Faithful, runnable implementations of two full session trading plans:

* **Full London Killzone Trading Plan** — ep 29 (``london``)
* **Trading Plan for the New York Killzone** — ep 30 (``new_york``)

Both episodes describe the *same* mechanical sequence ("the only thing that
changes is the time"): inside the session killzone window, a sweep→displacement
FVG (ep 12) in the HTF bias direction is the entry, the swept swing (covered
ITH/ITL) is the stop, and the opposing 4H PD array is the target. Each plan has
two day-profile variations:

    London  : Asia expansion      / Asia consolidation   (ep 29)
    New York: New York retracement / New York reversal    (ep 30)

mapped onto :class:`SessionVariation.EXPANSION` / ``.CONSOLIDATION``.

Quick start::

    from mmc.data import load
    from mmc.core.types import Timeframe
    from atoz.core import Direction
    import atoz.killzone_plans as kp

    df = load("EURUSD", Timeframe.M15).tail(3000)
    lon = kp.find_london_setups(df, bias=Direction.BEARISH)
    ny  = kp.find_new_york_setups(df)
    for s in lon:
        print(s.session.value, s.variation.value, s.direction.value,
              round(s.rr, 2), s.time)
"""

from .plan import (
    SessionSetup,
    SessionVariation,
    classify_session_variation,
    find_session_setups,
)
from .london import (
    asia_consolidation_setups,
    asia_expansion_setups,
    find_london_setups,
)
from .new_york import (
    find_new_york_setups,
    new_york_retracement_setups,
    new_york_reversal_setups,
)

__all__ = [
    # engine
    "SessionSetup", "SessionVariation",
    "find_session_setups", "classify_session_variation",
    # London (ep 29)
    "find_london_setups", "asia_expansion_setups", "asia_consolidation_setups",
    # New York (ep 30)
    "find_new_york_setups", "new_york_retracement_setups", "new_york_reversal_setups",
]

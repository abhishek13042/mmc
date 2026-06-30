"""atoz.economic — economic roadmap + LP/HP conditions (A-Z Guide ep 25-26).

ep 25  (roadmap.py)   — News tells you *when* to trade. The calendar and price
                        action must be **in agreement**; high-impact drivers
                        carry the day's volatility; trade the instruments related
                        to the news currency; blackout (no execution) ahead of /
                        during FOMC, NFP, CPI until 5 min after release.
ep 26  (conditions.py)— LP vs HP. HP = clear one-sidedness (100/0 arguments,
                        obvious drawn liquidity). LP = 50/50 bias (both sides,
                        even 90/10), chasing after an expansion took liquidity,
                        or trading ahead of CPI/NFP/FOMC. Rule: don't trade in LP.

No live calendar feed exists, so the roadmap operates on **user-supplied**
:class:`NewsEvent` objects. Pure functions over an OHLC DataFrame (DatetimeIndex,
broker/EET). Narrative-only parts (gut-feel timing, per-model data thresholds)
are noted in each module docstring and left to the caller.
"""

from .roadmap import (
    BLACKOUT_EVENTS,
    CURRENCY_INSTRUMENTS,
    Impact,
    NewsEvent,
    TradeWindow,
    annotate_roadmap,
    evaluate_bar,
    event_drives_symbol,
    events_for_symbol,
    events_on_day,
    in_blackout_window,
    is_expansion_day,
    price_action_in_agreement,
)
from .conditions import (
    Arguments,
    ConditionReport,
    Probability,
    ThreeCandleFVG,
    after_expansion_took_liquidity,
    classify_bar,
    classify_conditions,
    find_three_candle_fvgs,
    is_ahead_of_blackout,
)

__all__ = [
    # roadmap (ep 25)
    "Impact", "NewsEvent", "TradeWindow", "BLACKOUT_EVENTS", "CURRENCY_INSTRUMENTS",
    "event_drives_symbol", "events_for_symbol", "events_on_day", "is_expansion_day",
    "in_blackout_window", "evaluate_bar", "price_action_in_agreement", "annotate_roadmap",
    # conditions (ep 26)
    "Probability", "Arguments", "ConditionReport", "ThreeCandleFVG",
    "classify_conditions", "classify_bar", "after_expansion_took_liquidity",
    "is_ahead_of_blackout", "find_three_candle_fvgs",
]

"""Timing layer — *time = volatility* (transcript 09 — Time Trading).

Two kinds of time, mirroring the transcript:

Lower-timeframe time — **sessions / kill zones** (:mod:`mmc.timing.sessions`)
    ``in_killzone(timestamp, instrument="forex"|"index")`` — forex 02:00–10:00
    NY, index 09:30–16:00 NY. Plus ``KillZone`` / ``Instrument`` enums,
    ``killzone_window`` and ``to_newyork``.

Volatility profile from data (:mod:`mmc.timing.volatility`)
    ``volatility_by_hour(df)`` — average bar range per hour-of-day, and
    ``above_average_hours`` / ``is_volatile_hour`` to flag the volatile hours
    ("trade when volatility is above average").

Higher-timeframe time — **news / economic calendar** (:mod:`mmc.timing.news`)
    ``NewsEvent`` dataclass, ``Impact`` + ``BigThree`` enums, and the rule
    helpers ``is_big_three``, ``day_before_big_three_is_quiet``,
    ``weekly_profile``, ``real_volatility_day`` and ``affects_symbol``.

This layer depends only on :mod:`mmc.core` (it reuses ``Timeframe`` indirectly
via the loader) and pandas/numpy — no live feeds, no I/O.
"""

from __future__ import annotations

from .news import (
    CPI_NAME,
    FOMC_STATEMENT_NAME,
    NFP_NAME,
    BigThree,
    Impact,
    NewsEvent,
    affects_symbol,
    big_three_events,
    big_three_of,
    day_before_big_three_is_quiet,
    is_big_three,
    real_volatility_day,
    real_volatility_event,
    weekly_profile,
)
from .sessions import (
    DEFAULT_TZ,
    Instrument,
    KillZone,
    in_killzone,
    killzone_window,
    to_newyork,
)
from .volatility import (
    above_average_hours,
    bar_range,
    is_volatile_hour,
    true_range,
    volatility_by_hour,
)

__all__ = [
    # sessions / kill zones
    "Instrument",
    "KillZone",
    "DEFAULT_TZ",
    "in_killzone",
    "killzone_window",
    "to_newyork",
    # volatility profile
    "bar_range",
    "true_range",
    "volatility_by_hour",
    "above_average_hours",
    "is_volatile_hour",
    # news / economic calendar
    "Impact",
    "BigThree",
    "NewsEvent",
    "NFP_NAME",
    "FOMC_STATEMENT_NAME",
    "CPI_NAME",
    "is_big_three",
    "big_three_of",
    "big_three_events",
    "day_before_big_three_is_quiet",
    "real_volatility_event",
    "real_volatility_day",
    "weekly_profile",
    "affects_symbol",
]

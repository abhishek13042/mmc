"""News-event model — the *higher-timeframe* side of time (transcript 09).

transcript 09: higher-timeframe time **is** the economic calendar. News brings
volatility ("energy bars for the markets", ~4:42), and a currency with a
red-folder event is higher probability than one with none (~6:09). This module
models the **structure** of that calendar and MMC's rules over it — there is no
live feed in this repo, so callers supply lists of :class:`NewsEvent`.

Key rules modelled (transcript 09):

* **Impact / folder** — forexfactory colour codes (red = high). Arjo filters out
  yellow folders and CNY (~5:12). :class:`Impact`.
* **The big three** USD events to wait *after* (slippage risk, ~16:07): **NFP**
  (Non-Farm Employment Change, Friday), **USD FOMC Statement**, **USD CPI**.
  :class:`BigThree` + :func:`is_big_three`.
* **Day before a big-three is quiet** (~17:02): "the day before will also be
  less volatile ... a consolidation." :func:`day_before_big_three_is_quiet`.
* **Two big-three in one week** (~19:16): the **first** doesn't bring the real
  move; the **last** one does. :func:`weekly_profile` /
  :func:`real_volatility_day`.
* **affects_symbol** — a currency event affects any symbol containing that
  currency's code (~9:57: "AUD CHF ... has Australian dollar in the ticker name,
  it will be more volatile"). :func:`affects_symbol`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Iterable, List, Optional

import pandas as pd


class Impact(Enum):
    """forexfactory folder colour / event impact (transcript 09, ~5:12).

    Yellow (low) and grey (holiday/non-economic) are the ones Arjo filters out;
    red (high) events are the volatile, high-probability ones.
    """

    GREY = "grey"      # holiday / non-economic
    YELLOW = "yellow"  # low impact (filtered off)
    ORANGE = "orange"  # medium impact
    RED = "red"        # high impact (red folder)

    @property
    def is_red_folder(self) -> bool:
        return self is Impact.RED


# Canonical forexfactory event names for the big three (transcript 09, ~16:27).
NFP_NAME = "Non-Farm Employment Change"
FOMC_STATEMENT_NAME = "FOMC Statement"
CPI_NAME = "CPI"


class BigThree(Enum):
    """The three USD events to wait *after* — slippage risk (transcript 09).

    ``value`` is the canonical forexfactory event-name substring used to match a
    :class:`NewsEvent`. Note (~16:32): it is the **Non-Farm Employment Change**
    on Friday, *not* the Wednesday ADP, and the **FOMC Statement**, not the FOMC
    meeting minutes.
    """

    NFP = NFP_NAME
    FOMC_STATEMENT = FOMC_STATEMENT_NAME
    CPI = CPI_NAME

    @property
    def event_name(self) -> str:
        return self.value


@dataclass
class NewsEvent:
    """A single economic-calendar event (transcript 09).

    Attributes
    ----------
    currency:
        ISO-ish currency code, e.g. ``"USD"``, ``"AUD"`` (upper-cased).
    name:
        forexfactory event name, e.g. ``"Non-Farm Employment Change"``.
    timestamp:
        Release time. Stored as a :class:`pandas.Timestamp`; the transcript uses
        New-York-local time.
    impact:
        Folder colour / :class:`Impact` (default RED — the events MMC cares
        about). A plain string colour is accepted and coerced.
    """

    currency: str
    name: str
    timestamp: pd.Timestamp
    impact: Impact = Impact.RED

    def __post_init__(self) -> None:
        self.currency = str(self.currency).upper()
        self.timestamp = pd.Timestamp(self.timestamp)
        if not isinstance(self.impact, Impact):
            self.impact = Impact(str(self.impact).lower())

    @property
    def date(self) -> date:
        return self.timestamp.date()

    @property
    def is_red_folder(self) -> bool:
        return self.impact.is_red_folder


def big_three_of(event: NewsEvent) -> Optional[BigThree]:
    """Return which :class:`BigThree` ``event`` is, or ``None``.

    A big-three event is **USD** and its name contains the canonical event name
    (case-insensitive). ADP / FOMC-minutes etc. do not match.
    """
    if event.currency != "USD":
        return None
    name = event.name.casefold()
    for member in BigThree:
        if member.event_name.casefold() in name:
            return member
    return None


def is_big_three(event: NewsEvent) -> bool:
    """Is ``event`` one of the big three USD events? (transcript 09, ~16:07)"""
    return big_three_of(event) is not None


def big_three_events(events: Iterable[NewsEvent]) -> List[NewsEvent]:
    """Filter ``events`` to the big-three ones, sorted by timestamp."""
    out = [e for e in events if is_big_three(e)]
    out.sort(key=lambda e: e.timestamp)
    return out


def day_before_big_three_is_quiet(
    day, events: Iterable[NewsEvent]
) -> bool:
    """Is ``day`` the calendar day *before* a big-three event? (transcript 09)

    ~17:02: "When we have these big three news events, the day before will also
    be less volatile ... a consolidation." Returns ``True`` when at least one
    big-three event falls on the day immediately after ``day``.

    ``day`` may be a date, datetime, or anything :class:`pandas.Timestamp`
    accepts; only the calendar date is used.
    """
    target = pd.Timestamp(day).normalize().date()
    for e in big_three_events(events):
        prev_day = (e.timestamp.normalize() - pd.Timedelta(days=1)).date()
        if prev_day == target:
            return True
    return False


def real_volatility_event(events: Iterable[NewsEvent]) -> Optional[NewsEvent]:
    """The big-three event that brings the *real* move for a set of events.

    ~19:16: if two big-three events fall in one week, the **first** won't bring
    the real volatility — the **last** one will. So this returns the **latest**
    big-three event (or ``None`` if there are none).
    """
    bt = big_three_events(events)
    return bt[-1] if bt else None


def real_volatility_day(events: Iterable[NewsEvent]) -> Optional[date]:
    """The calendar day that brings the real move (transcript 09, ~19:16).

    The date of the last big-three event of the supplied set, or ``None``.
    """
    event = real_volatility_event(events)
    return event.date if event is not None else None


def weekly_profile(events: Iterable[NewsEvent]) -> dict:
    """Summarise a week's events into MMC's "weekly profile" (transcript 09).

    Returns a dict with:

    * ``big_three`` — the big-three :class:`NewsEvent` list (sorted).
    * ``real_volatility_event`` — the last big-three event (the real move), or
      ``None``.
    * ``real_volatility_day`` — its calendar date, or ``None``.
    * ``quiet_days`` — sorted dates that are the day *before* a big-three event
      (expected consolidation).

    Operates purely on the supplied list; nothing is fetched.
    """
    events = list(events)
    bt = big_three_events(events)
    real = bt[-1] if bt else None
    quiet = sorted(
        {(e.timestamp.normalize() - pd.Timedelta(days=1)).date() for e in bt}
    )
    return {
        "big_three": bt,
        "real_volatility_event": real,
        "real_volatility_day": real.date if real is not None else None,
        "quiet_days": quiet,
    }


def affects_symbol(event: NewsEvent, symbol: str) -> bool:
    """Does ``event``'s currency appear in ``symbol``? (transcript 09, ~9:57)

    A currency event affects any instrument whose ticker contains that currency
    code: an AUD event affects ``AUDCHF`` and ``AUDUSD``; a USD event affects
    ``EURUSD`` and ``XAUUSD`` (gold is priced in USD). Matching is a simple
    case-insensitive substring test on the currency code.
    """
    return event.currency.upper() in str(symbol).upper()

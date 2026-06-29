"""Sessions / kill zones — the *lower-timeframe* side of time (transcript 09).

transcript 09 — Time Trading: "Time is volatility." There are two kinds of time:

* **Higher-timeframe time** = the economic calendar / news events
  (see :mod:`mmc.timing.news`).
* **Lower-timeframe time** = sessions / **kill zones** — the windows of the day
  where volatility concentrates. (~2:38: "Lower timeframe time refers to
  sessions or kill zones.")

The transcript states all times in **Eastern / New York local time** (~5:26:
"when I refer to any time, it is Eastern time, New York local time"). We model
the two windows MMC cares about:

* **Forex kill zone:** ``02:00`` – ``10:00`` New York (London open through the
  morning New York session — the most volatile forex hours).
* **Index kill zone:** ``09:30`` – ``16:00`` New York (equities cash-session
  open through bond-market close).

Timezone handling (be deliberate here):

* A *naive* timestamp (no ``tzinfo``) is **assumed to already be New York local
  time** and compared directly against the window — this matches how the raw
  MMC CSVs and TradingView are configured.
* A *tz-aware* timestamp is **converted** into ``tz`` (default
  ``America/New_York``) first, then compared. So a UTC timestamp is correctly
  localised before the kill-zone test.
"""

from __future__ import annotations

from datetime import time
from enum import Enum
from typing import Tuple

import pandas as pd

DEFAULT_TZ = "America/New_York"


class Instrument(Enum):
    """Which kill-zone window applies (transcript 09)."""

    FOREX = "forex"
    INDEX = "index"


class KillZone(Enum):
    """The kill-zone windows, as ``(start, end)`` New-York-local times.

    Windows are **half-open** ``[start, end)``: a timestamp exactly at ``start``
    is inside, one exactly at ``end`` is outside.
    """

    FOREX = (time(2, 0), time(10, 0))   # 02:00–10:00 NY
    INDEX = (time(9, 30), time(16, 0))  # 09:30–16:00 NY

    @property
    def start(self) -> time:
        return self.value[0]

    @property
    def end(self) -> time:
        return self.value[1]

    def contains(self, t: time) -> bool:
        """Is wall-clock ``t`` inside this half-open window?"""
        return self.start <= t < self.end


def _resolve_killzone(instrument) -> KillZone:
    """Map a string / :class:`Instrument` / :class:`KillZone` to a KillZone."""
    if isinstance(instrument, KillZone):
        return instrument
    if isinstance(instrument, Instrument):
        return KillZone[instrument.name]
    key = str(instrument).strip().upper()
    try:
        return KillZone[key]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(
            f"unknown instrument {instrument!r}; expected 'forex' or 'index'"
        ) from exc


def killzone_window(instrument: str = "forex") -> Tuple[time, time]:
    """Return the ``(start, end)`` New-York-local times for ``instrument``."""
    kz = _resolve_killzone(instrument)
    return kz.start, kz.end


def to_newyork(timestamp, tz: str = DEFAULT_TZ) -> pd.Timestamp:
    """Return ``timestamp`` as a New-York-local :class:`pandas.Timestamp`.

    Naive timestamps are **assumed to already be** ``tz`` local time and are
    returned unchanged (still naive). Aware timestamps are converted to ``tz``.
    """
    ts = pd.Timestamp(timestamp)
    if ts.tzinfo is None:
        return ts
    return ts.tz_convert(tz)


def in_killzone(timestamp, instrument: str = "forex", tz: str = DEFAULT_TZ) -> bool:
    """Is ``timestamp`` inside the kill zone for ``instrument``? (transcript 09)

    Parameters
    ----------
    timestamp:
        Anything :class:`pandas.Timestamp` accepts. If naive, it is assumed to
        be ``tz`` (New York) local time; if tz-aware, it is converted to ``tz``
        before the comparison.
    instrument:
        ``"forex"`` (02:00–10:00 NY) or ``"index"`` (09:30–16:00 NY). Also
        accepts :class:`Instrument` / :class:`KillZone` members.
    tz:
        The local timezone the windows are defined in (default New York).
    """
    kz = _resolve_killzone(instrument)
    ts = to_newyork(timestamp, tz=tz)
    return kz.contains(ts.time())

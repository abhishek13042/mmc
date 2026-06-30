"""Killzones (A-Z Guide ep 16, + indices ep 17).

> Killzones are fixed in **New York local time** (the algorithm references NY,
> so they do NOT shift with London DST). Asia 20:00–00:00, London 02:00–05:00,
> New York 07:00–10:00, London Close 10:00–12:00; the **NY midnight open** is
> 00:00. The economic calendar matters more than the killzone — volatility lands
> on the news day.  — ep 16

> For **indices** (ES/NQ) the equities open at **09:30 NY** (and the 08:30 macro)
> is the key killzone — that is where the cleanest Judas swing / expansion
> happens.  — ep 17

Broker note: this project's data is **EET (UTC+2/+3)**. Because EET and NY both
observe DST, broker = NY + 7 *constantly*. Broker-time killzones therefore:
Asia 03:00–07:00, London 09:00–12:00, NY 14:00–17:00, London Close 17:00–19:00,
equities open 16:30, midnight open 07:00.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd

# NY-to-broker(EET) constant offset (both observe DST together).
NY_TO_BROKER = 7


class Killzone(Enum):
    ASIA = "asia"
    LONDON = "london"
    NEW_YORK = "new_york"
    LONDON_CLOSE = "london_close"
    EQUITIES_OPEN = "equities_open"   # indices (ep 17): 09:30 NY
    NONE = "none"


# (start_hour, end_hour) in NEW YORK local time. Asia wraps midnight.
_KZ_NY = {
    Killzone.ASIA: (20, 24),
    Killzone.LONDON: (2, 5),
    Killzone.NEW_YORK: (7, 10),
    Killzone.LONDON_CLOSE: (10, 12),
}
MIDNIGHT_OPEN_NY = 0
EQUITIES_OPEN_NY = 9.5   # 09:30


@dataclass
class Session:
    kz: Killzone
    start_ny: float
    end_ny: float

    @property
    def start_broker(self) -> float:
        return (self.start_ny + NY_TO_BROKER) % 24

    @property
    def end_broker(self) -> float:
        return (self.end_ny + NY_TO_BROKER) % 24


def killzone_of(hour_ny: float) -> Killzone:
    """Return the killzone for a New-York-local hour."""
    for kz, (s, e) in _KZ_NY.items():
        if s <= hour_ny < e:
            return kz
    return Killzone.NONE


def killzone_of_broker(hour_broker: float) -> Killzone:
    """Return the killzone for a broker-time (EET) hour."""
    return killzone_of((hour_broker - NY_TO_BROKER) % 24)


def annotate_killzones(df: pd.DataFrame, broker_time: bool = True) -> pd.Series:
    """Return a Series labelling each bar's killzone.

    ``broker_time=True`` (default) treats the DatetimeIndex as broker/EET time
    (this project's data); set False if the index is already NY local.
    """
    hours = df.index.hour + df.index.minute / 60.0
    fn = killzone_of_broker if broker_time else killzone_of
    return pd.Series([fn(h).value for h in hours], index=df.index)


def is_equities_open(timestamp: pd.Timestamp, broker_time: bool = True, window_min: int = 30) -> bool:
    """True within ``window_min`` minutes of the indices equities open (ep 17)."""
    hour = timestamp.hour + timestamp.minute / 60.0
    open_h = (EQUITIES_OPEN_NY + NY_TO_BROKER) % 24 if broker_time else EQUITIES_OPEN_NY
    return abs(hour - open_h) <= window_min / 60.0

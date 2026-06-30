"""Economic Roadmap — news drivers tell you *when* to trade (A-Z Guide ep 25).

> Using the economic calendar as your roadmap is when the economic calendar and
> price action itself are **in agreement** — that is exactly when you want to be
> trading. ... News drivers bring in volatility. ... For us to trade we need
> volatility. Kill zones give volatility for a *session* (scalps); the economic
> calendar tells you whether the **day itself** will expand. Trade the
> instruments related to the news currency (USD news → gold, ES, NQ, YM, EU, GU,
> all majors). Price action being in agreement: if we are hovering *above a
> discount array* on a day that has a supporting news driver, that is when the
> calendar and price action agree.  — ep 25

> **Exception (listen carefully):** ahead of / during **FOMC, NFP, CPI** you do
> NOT execute. Only after the news release itself — and not within five minutes
> of the release. Otherwise you risk getting *slipped*. The rest of the
> high-impact events (PMI, PPI, retail sales, unemployment claims) are fine to
> trade before, during or after — the day is already volatile and the news is
> a smoke screen / already priced in.  — ep 25

We have no live calendar feed, so the roadmap is modelled from **user-supplied**
events: a :class:`NewsEvent` dataclass and pure functions that flag which day is
the expected expansion day and whether a given bar sits in a tradeable window.

What is codifiable here:
    * the slippage-blackout rule for FOMC/NFP/CPI (exact, mechanical);
    * "instrument related to the news currency" (currency membership);
    * the day-of-week expansion flag (a day carrying a high-impact driver);
    * price-action-agreement (a supporting PD array on the news day) when the
      caller passes the relevant zones.
Narrative-only (NOT codified): *why* the banks pre-price the news, and the
discretionary read of "the cleanest, most beautiful price action".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Iterable, List, Optional, Sequence

import pandas as pd

from atoz.core.types import Direction, Zone


class Impact(Enum):
    """News-driver impact. Only HIGH drivers carry the day's volatility (ep 25)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# The three events that trigger the slippage blackout (ep 25 — "don't blame me
# if you mess up"). Matched case-insensitively against NewsEvent.name.
BLACKOUT_EVENTS = ("fomc", "nfp", "cpi")
# Friendly aliases that map to a blackout event.
_BLACKOUT_ALIASES = {
    "non farm payrolls": "nfp",
    "non-farm payrolls": "nfp",
    "nonfarm payrolls": "nfp",
    "consumer price index": "cpi",
    "federal open market committee": "fomc",
    "fed funds rate": "fomc",
    "interest rate decision": "fomc",
}

# Instruments related to each currency (ep 25 — "all the USD instruments ...
# ES, NASDAQ, YM, Gold, Silver, EU, GU, all the major forex pairs"). The map is
# currency → the symbols whose moves that currency's news drives. Symbols are
# upper-cased and matched as substrings, so "EURUSD" matches USD and EUR.
CURRENCY_INSTRUMENTS = {
    "USD": (
        "ES", "NQ", "NASDAQ", "YM", "DOW", "SPX", "US30", "US500", "NAS100",
        "XAUUSD", "GOLD", "XAGUSD", "SILVER",
        "EURUSD", "EU", "GBPUSD", "GU", "USDJPY", "UJ", "USDCAD", "UC",
        "USDCHF", "AUDUSD", "AU", "NZDUSD",
    ),
    "EUR": ("EURUSD", "EU", "EURJPY", "EURGBP", "EURCHF", "EURAUD"),
    "GBP": ("GBPUSD", "GU", "GBPJPY", "GJ", "EURGBP", "GBPCHF"),
    "JPY": ("USDJPY", "UJ", "EURJPY", "GBPJPY", "GJ", "CADJPY", "AUDJPY"),
    "CAD": ("USDCAD", "UC", "CADJPY", "EURCAD"),
    "CHF": ("USDCHF", "EURCHF", "GBPCHF"),
    "AUD": ("AUDUSD", "AU", "AUDJPY", "EURAUD", "AUDNZD"),
    "NZD": ("NZDUSD", "AUDNZD", "NZDJPY"),
}


@dataclass
class NewsEvent:
    """A single economic-calendar driver, supplied by the user (ep 25).

    ``time`` is the release timestamp (broker/EET, matching this project's
    OHLC index). ``currency`` is the 3-letter code (e.g. "USD"). ``name`` is the
    event title (e.g. "CPI", "Empire State Manufacturing Index").
    """

    time: pd.Timestamp
    currency: str
    name: str
    impact: Impact = Impact.HIGH

    def __post_init__(self) -> None:
        self.time = pd.Timestamp(self.time)
        self.currency = self.currency.upper()

    @property
    def day(self) -> pd.Timestamp:
        """The calendar date (normalised midnight) of the release."""
        return self.time.normalize()

    @property
    def is_blackout(self) -> bool:
        """True for FOMC / NFP / CPI — the slippage-blackout events (ep 25)."""
        n = self.name.strip().lower()
        if n in _BLACKOUT_ALIASES:
            n = _BLACKOUT_ALIASES[n]
        return any(b in n for b in BLACKOUT_EVENTS)

    def drives(self, symbol: str) -> bool:
        """True if this event's currency drives ``symbol`` (ep 25 instrument map)."""
        return event_drives_symbol(self, symbol)


def event_drives_symbol(event: NewsEvent, symbol: str) -> bool:
    """Does ``event``'s currency drive ``symbol``? (ep 25 — trade the pairs and
    instruments closely related to the news currency)."""
    sym = symbol.upper().replace("/", "").replace("_", "")
    related = CURRENCY_INSTRUMENTS.get(event.currency, ())
    # Direct currency-code membership (e.g. CAD in USDCAD / CADJPY).
    if event.currency in sym:
        return True
    return any(sym == r or sym in r or r in sym for r in related)


def events_for_symbol(events: Iterable[NewsEvent], symbol: str) -> List[NewsEvent]:
    """Filter ``events`` to those whose currency drives ``symbol``."""
    return [e for e in events if event_drives_symbol(e, symbol)]


def events_on_day(events: Iterable[NewsEvent], day: pd.Timestamp) -> List[NewsEvent]:
    """All events whose release date equals ``day`` (date compared, time ignored)."""
    d = pd.Timestamp(day).normalize()
    return [e for e in events if e.day == d]


def is_expansion_day(
    events: Iterable[NewsEvent],
    day: pd.Timestamp,
    symbol: Optional[str] = None,
    min_impact: Impact = Impact.HIGH,
) -> bool:
    """Is ``day`` an expected expansion day?  (ep 25)

    A day is an expansion day when it carries at least one high-impact driver for
    the traded instrument's currency — "that is the day where we can actually
    explode higher or lower ... not done by our kill zones, done by the economic
    calendar." If ``symbol`` is given, only drivers that drive that symbol count.
    """
    rank = {Impact.LOW: 0, Impact.MEDIUM: 1, Impact.HIGH: 2}
    todays = events_on_day(events, day)
    if symbol is not None:
        todays = [e for e in todays if event_drives_symbol(e, symbol)]
    return any(rank[e.impact] >= rank[min_impact] for e in todays)


@dataclass
class TradeWindow:
    """The result of evaluating a bar against the roadmap rules (ep 25)."""

    timestamp: pd.Timestamp
    tradeable: bool
    expansion_day: bool          # day carries a high-impact driver
    in_blackout: bool            # inside an FOMC/NFP/CPI blackout window
    reason: str
    events: List[NewsEvent] = field(default_factory=list)


def in_blackout_window(
    timestamp: pd.Timestamp,
    events: Iterable[NewsEvent],
    symbol: Optional[str] = None,
    post_release_minutes: int = 5,
) -> Optional[NewsEvent]:
    """Return the FOMC/NFP/CPI event whose blackout covers ``timestamp``, else None.

    The blackout (ep 25) runs from the *start of the release day* up to
    ``post_release_minutes`` (default 5) after the release. Inside it you do not
    execute. After the window — i.e. >5 min past the release — it is fine.
    "ahead of the news event ... and ... the news event itself five minutes after
    the release ... only if it's after the news release itself."
    """
    ts = pd.Timestamp(timestamp)
    for e in events:
        if not e.is_blackout:
            continue
        if symbol is not None and not event_drives_symbol(e, symbol):
            continue
        # Block from the start of the release day until 5 min after release.
        start = e.day
        end = e.time + timedelta(minutes=post_release_minutes)
        if start <= ts <= end:
            return e
    return None


def evaluate_bar(
    timestamp: pd.Timestamp,
    events: Iterable[NewsEvent],
    symbol: Optional[str] = None,
    pa_supports: Optional[bool] = None,
    post_release_minutes: int = 5,
) -> TradeWindow:
    """Apply the ep-25 roadmap to a single bar.

    Rules, in order (ep 25):
      1. If the bar is inside an FOMC/NFP/CPI blackout → NOT tradeable (slippage).
      2. Otherwise the bar is tradeable only on an **expansion day** (a day that
         carries a high-impact driver for the instrument's currency) ...
      3. ... *and* price action must be in agreement. ``pa_supports`` is the
         caller's price-action-agreement flag (e.g. from
         :func:`price_action_in_agreement`). If left None, agreement is not
         checked here (the caller asserts only the calendar side).
    """
    ts = pd.Timestamp(timestamp)
    evs = events_on_day(events, ts)
    if symbol is not None:
        evs = [e for e in evs if event_drives_symbol(e, symbol)]

    blackout = in_blackout_window(ts, events, symbol, post_release_minutes)
    if blackout is not None:
        return TradeWindow(
            ts, tradeable=False, expansion_day=True, in_blackout=True,
            reason=f"blackout: {blackout.name} (no execution until {post_release_minutes}m after release)",
            events=evs,
        )

    expansion = is_expansion_day(events, ts, symbol)
    if not expansion:
        return TradeWindow(
            ts, tradeable=False, expansion_day=False, in_blackout=False,
            reason="no high-impact driver today — day likely consolidates (kill zone only)",
            events=evs,
        )

    if pa_supports is False:
        return TradeWindow(
            ts, tradeable=False, expansion_day=True, in_blackout=False,
            reason="expansion day but price action NOT in agreement",
            events=evs,
        )

    reason = "expansion day"
    if pa_supports is True:
        reason = "expansion day AND price action in agreement"
    return TradeWindow(
        ts, tradeable=True, expansion_day=True, in_blackout=False,
        reason=reason, events=evs,
    )


def price_action_in_agreement(
    price: float,
    direction: Direction,
    arrays: Sequence[Zone],
    tolerance: float = 0.0,
) -> bool:
    """Is price action in agreement with a bullish/bearish bias? (ep 25)

    Agreement (ep 25): we are "hovering above a discount array" (for a bullish
    expansion) or below a premium array (for a bearish one), so the supporting PD
    array sits just beyond price in the trade's direction. ``arrays`` are the PD
    arrays the caller is watching (e.g. an FVG / order block). Returns True if a
    same-direction array sits on the supporting side of ``price``.

      * BULLISH: a discount (bullish) array at/below price (we hover above it).
      * BEARISH: a premium (bearish) array at/above price (we hover below it).
    """
    for z in arrays:
        if z.direction is not direction:
            continue
        if direction is Direction.BULLISH and z.top <= price * (1 + tolerance):
            return True
        if direction is Direction.BEARISH and z.bottom >= price * (1 - tolerance):
            return True
    return False


def annotate_roadmap(
    df: pd.DataFrame,
    events: Iterable[NewsEvent],
    symbol: Optional[str] = None,
    post_release_minutes: int = 5,
) -> pd.DataFrame:
    """Annotate every bar of ``df`` (DatetimeIndex, broker/EET) with the roadmap.

    Returns a frame indexed like ``df`` with columns:
        expansion_day, in_blackout, tradeable, reason.
    Price-action agreement is left to the caller (not checked here), so
    ``tradeable`` reflects the calendar side only: expansion day and not in a
    blackout window.
    """
    events = list(events)
    rows = []
    for ts in df.index:
        tw = evaluate_bar(ts, events, symbol, pa_supports=None,
                          post_release_minutes=post_release_minutes)
        rows.append({
            "expansion_day": tw.expansion_day,
            "in_blackout": tw.in_blackout,
            "tradeable": tw.tradeable,
            "reason": tw.reason,
        })
    return pd.DataFrame(rows, index=df.index)

"""Advanced scalping — the "do it the right way" play style (A-Z Guide ep 37).

> "The trading industry has been lying to you ... including scalping ... a lot of
> people are just going into the one minute time frame and they take every one
> minute fair value gap without any reason behind it ... that will not be
> sustainable ... What is the difference between one one-minute fair value gap
> and the other one-minute fair value gap? It's what happened before that. It's
> the **boundary** that needs to get hit first."  — ep 37

The episode's thesis: a lower-timeframe (1-minute or 5-minute) entry is only
valid when it sits inside a **higher-timeframe boundary** (a 1-hour or 15-minute
PD array) which is itself in context of the **daily bias**, and price tapped that
boundary **at the right time** (a killzone or a news release). Without the
boundary every LTF FVG looks identical and you take 10 losses for 1 win.

Faithful definitions, quoted from the ep-37 transcript
------------------------------------------------------

The boundary requirement (the core idea):

    > "if we have no boundary ... we can take every one minute fair value gap as
    > an entry. Does that mean it's a good entry? Absolutely not. What is the
    > boundary that happens before that? That is what differentiates a weak one
    > minute fair value gap from a strong one minute fair value gap. There needs
    > to be a boundary before that. The boundary is a **one hour PD array or a 15
    > minute PD array**, again when coming off of ideally a daily fair value gap
    > or a daily PD [array]. So first off you need to have the daily somewhat
    > agreeing to your idea to go into the one hour."

The daily bias gate:

    > "first off, we need to understand some kind of daily bias ... you're looking
    > at the stronger fair value gaps ... this fair value gap is weaker than that
    > fair value gap so this is the stronger fair value gap ... between this fair
    > value gap and that next target ... you're letting the one hour guide you ...
    > to your next target."

Timing into the boundary (the sting):

    > "we're having that PD ray ... which we sting into at the right time. So that
    > is a kill zone or that is news. When you have that and you see an entry
    > pattern right there at that moment, that is where you want to get involved
    > ... news stings into that one hour order block with that fair value gap ...
    > you wait for NFP to show where it's going ... then you just wait for your
    > entry pattern after the NFP release."

The lower-timeframe trigger (1-minute OR 5-minute — both are scalping):

    > "if we dive into the one minute on that one hour fair value gap ... you want
    > to wait for your ST and then you want to wait for your new fair value gap
    > lower ... that is where you can place your entry on the overlapping part
    > with those lows ... and you cover the intermediate term high ... what do you
    > target — since you are scalping you have a close target, you get in you get
    > out, ideally at first a 1 to 2 ... you can also use the five minute ... you
    > can achieve the exact same entry ... and it would still be scalping."

15-minute boundary needs less confirmation:

    > "after a one hour PD ray has been reached then we can go potentially into
    > the 15 minute ... we have a new PD ray to work with, aka a new boundary, a
    > new reason to go into the lower time frame to scalp ... 15 minute PD ray,
    > one minute ST is enough ... when you're using one hour PD ray you would need
    > more confirmation."

Mechanical encoding
-------------------
A scalp entry is faithful only when ALL of these hold (the episode is emphatic
that the boundary + daily agreement is what separates a "strong" from a "weak"
1-minute FVG):

  1. **Daily bias** — a direction from the stronger daily FVG (delegated to the
     simple stronger-FVG rule the episode references).
  2. **Boundary** — a 1-hour OR 15-minute PD array (here an FVG) of the *same*
     direction as the daily bias, that price has **tapped** ("the boundary that
     needs to get hit first").
  3. **Timing** — price stung into the boundary inside a killzone or near a news
     time (reused from ``atoz.timing``). Optional but the episode's confluence.
  4. **LTF trigger** — drop to the 1-minute or 5-minute and take the ep-23 ST
     entry (ST + new FVG + overlapping part), cover the intermediate-term
     high/low, target a 1-to-2.

The LTF trigger is reused verbatim from ``atoz.st_model.find_st_setups``; this
module supplies the *boundary + daily-bias + timing* gate that ep 37 says is the
whole point. Pure functions over OHLC DataFrames; no look-ahead.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pandas as pd

from atoz.core.fvg import FVG, find_fvgs
from atoz.core.types import Candles, Direction, Zone
from atoz.st_model import STSetup, find_st_setups
from atoz.timing import Killzone, annotate_killzones


class ScalpEntryTF(Enum):
    """The lower timeframe the scalp is executed on (ep 37 — "1 minute OR 5
    minute ... it would still be scalping")."""

    ONE_MIN = "1m"
    FIVE_MIN = "5m"


class BoundaryTF(Enum):
    """The higher-timeframe boundary the scalp must sit inside (ep 37)."""

    ONE_HOUR = "1h"
    FIFTEEN_MIN = "15m"


# --------------------------------------------------------------------------- #
# 1) Daily bias — the stronger daily fair value gap (ep 36/37 reference)
# --------------------------------------------------------------------------- #


def daily_bias(daily_df: pd.DataFrame, lookback: int = 30) -> Optional[Direction]:
    """A simple daily bias from the *stronger* daily fair value gap (ep 37).

    > "you're looking at the stronger fair value gaps ... this fair value gap is
    > weaker than that fair value gap so this is the stronger fair value gap."

    The episode defines a "strong" daily FVG as one that is **respected** — price
    wicks into it and continues (it is not traded back through). We take the most
    recent respected daily FVG within ``lookback`` bars and return its direction
    as the bias. Returns ``None`` when no clear (respected) daily FVG exists —
    faithful to "we don't really have the daily agreeing ... not really as strong
    a fair value gap" (in which case you should not scalp).
    """
    c = Candles.of(daily_df)
    fvgs = [f for f in find_fvgs(daily_df) if f.index >= c.n - lookback]
    best: Optional[FVG] = None
    for f in fvgs:
        # "respected" = after it formed, price does NOT close back through it
        # (a bullish FVG holds if no later candle closes below its bottom).
        respected = True
        for k in range(f.c3_index + 1, c.n):
            if f.direction is Direction.BULLISH and c.close[k] < f.bottom:
                respected = False
                break
            if f.direction is Direction.BEARISH and c.close[k] > f.top:
                respected = False
                break
        if respected:
            best = f  # keep the most recent respected FVG
    return best.direction if best is not None else None


# --------------------------------------------------------------------------- #
# 2) Boundary — a 1h / 15m PD array, tapped, in context of the daily bias
# --------------------------------------------------------------------------- #


@dataclass
class Boundary:
    """The HTF PD array a scalp must sit inside (ep 37 "the boundary that needs
    to get hit first")."""

    timeframe: BoundaryTF
    direction: Direction
    array: FVG               # the 1h/15m PD array (an FVG)
    tapped_index: int        # bar (in the boundary df) price tapped the array
    tapped_time: pd.Timestamp
    tapped_killzone: Killzone
    on_news: bool            # tapped near a provided news time (optional)


def find_boundaries(
    boundary_df: pd.DataFrame,
    timeframe: BoundaryTF,
    bias: Direction,
    news_times: Optional[List[pd.Timestamp]] = None,
    news_window_min: int = 30,
    require_killzone: bool = False,
) -> List[Boundary]:
    """Find ep-37 boundaries: PD arrays (FVGs) on the 1h/15m that agree with the
    daily ``bias`` and that price has **tapped** at the right time.

    > "The boundary is a one hour PD array or a 15 minute PD array ... when coming
    > off of ideally a daily ... PD [array]. So first off you need to have the
    > daily somewhat agreeing."

    "Tapped" = a later candle trades into the FVG's zone (price stings into the
    PD array). The tap's killzone / news proximity is recorded (ep 37 — "we sting
    into at the right time ... a kill zone or ... news"). With
    ``require_killzone`` set, only taps inside a killzone (or near news) are kept.
    """
    c = Candles.of(boundary_df)
    kz = annotate_killzones(boundary_df, broker_time=True)
    fvgs = [f for f in find_fvgs(boundary_df) if f.direction is bias]
    news_times = news_times or []

    out: List[Boundary] = []
    for f in fvgs:
        # first tap after the FVG forms (price stings into the array).
        tap = None
        for k in range(f.c3_index + 1, c.n):
            if f.direction is Direction.BULLISH and c.low[k] <= f.top:
                tap = k
                break
            if f.direction is Direction.BEARISH and c.high[k] >= f.bottom:
                tap = k
                break
        if tap is None:
            continue

        ts = boundary_df.index[tap]
        tap_kz = Killzone(kz.iloc[tap])
        on_news = any(
            abs((ts - nt).total_seconds()) <= news_window_min * 60 for nt in news_times
        )
        if require_killzone and tap_kz is Killzone.NONE and not on_news:
            continue

        out.append(
            Boundary(
                timeframe=timeframe, direction=bias, array=f,
                tapped_index=tap, tapped_time=ts, tapped_killzone=tap_kz,
                on_news=on_news,
            )
        )
    out.sort(key=lambda b: b.tapped_index)
    return out


# --------------------------------------------------------------------------- #
# 3) The scalp entry — LTF ST trigger gated by the boundary
# --------------------------------------------------------------------------- #


@dataclass
class ScalpEntry:
    """A faithful ep-37 advanced-scalping entry.

    The four things the instructor names plus the gate that makes it "strong":

    ``entry_tf``      1-minute or 5-minute (both are scalping).
    ``direction``     matches the daily bias and the boundary.
    ``entry_price``   the overlapping-part / FVG edge (off the LTF ST).
    ``stop_loss``     beyond the intermediate-term high/low.
    ``take_profit``   the close 1-to-2 scalp target.
    ``boundary``      the 1h/15m PD array the entry sits inside (the gate).
    ``st_setup``      the reused ep-23 LTF ST trigger.
    ``entry_time``    timestamp of the confirming LTF bar.
    ``killzone``      killzone the entry confirmed in.
    ``on_news``       boundary was tapped near a news time.
    """

    entry_tf: ScalpEntryTF
    direction: Direction
    entry_price: float
    stop_loss: float
    take_profit: float
    boundary: Boundary
    st_setup: STSetup
    entry_time: pd.Timestamp
    killzone: Killzone
    on_news: bool

    @property
    def rr(self) -> float:
        risk = abs(self.entry_price - self.stop_loss)
        return abs(self.take_profit - self.entry_price) / risk if risk else 0.0


def _target_at_rr(entry: float, stop: float, rr: float, bullish: bool) -> float:
    risk = abs(entry - stop)
    return entry + rr * risk if bullish else entry - rr * risk


def find_scalp_entries(
    ltf_df: pd.DataFrame,
    boundary: Boundary,
    entry_tf: ScalpEntryTF = ScalpEntryTF.ONE_MIN,
    target_rr: float = 2.0,
    after_tap_only: bool = True,
) -> List[ScalpEntry]:
    """Detect ep-37 scalp entries on the LTF, gated by a single ``boundary``.

    This is the deliverable: the exact lower-timeframe trigger the instructor
    uses. On the 1-minute (or 5-minute) DataFrame we take the ep-23 ST entries
    (ST + new FVG + overlapping part, cover the intermediate-term high/low) and
    keep ONLY those that:

      * match the boundary (= daily-bias) direction; and
      * have their entry price **inside the boundary PD-array zone** — i.e. the
        "boundary that needs to get hit first" (this is what differentiates a
        strong LTF FVG from a random one); and
      * (default ``after_tap_only``) confirm at/after the boundary was tapped, so
        the entry comes *after* price stung into the PD array at the right time.

    The target defaults to a 1-to-2 (ep 37 "ideally at first a 1 to 2").
    """
    sts = find_st_setups(ltf_df)
    kz = annotate_killzones(ltf_df, broker_time=True)
    out: List[ScalpEntry] = []
    bullish = boundary.direction is Direction.BULLISH
    arr = boundary.array

    for st in sts:
        if st.direction is not boundary.direction:
            continue
        # entry must sit inside the boundary PD-array zone (the gate).
        if not (arr.bottom <= st.entry_price <= arr.top):
            continue

        ts = ltf_df.index[st.index]
        if after_tap_only and ts < boundary.tapped_time:
            continue

        entry = st.entry_price
        stop = st.stop_loss
        if abs(entry - stop) < 1e-9:
            continue
        tp = _target_at_rr(entry, stop, target_rr, bullish)

        out.append(
            ScalpEntry(
                entry_tf=entry_tf, direction=boundary.direction,
                entry_price=float(entry), stop_loss=float(stop),
                take_profit=float(tp), boundary=boundary, st_setup=st,
                entry_time=ts, killzone=Killzone(kz.iloc[st.index]),
                on_news=boundary.on_news,
            )
        )
    out.sort(key=lambda s: s.entry_time)
    return out

"""Swing trading around a full-time job — the "Lost Art" play style (A-Z Guide ep 35).

> "swing trading is a lost art ... a lot of people are just busy throughout the
> day. They don't have time to scalp ... How can I get to a swing trade? ...
> since everything I do ... is very fractal, I'm going to go over exactly how you
> can get to a swing trading plan ... where you hold trades over potentially even
> a couple of hours ... think about catching the weekly range ... the monthly
> range."  — ep 35

The episode is a *set-and-forget / limit-order* play style for someone with a
full-time job. The work is done **on the weekend** (scout the high-probability
pairs and the higher-timeframe context), then during the busy week you only have
to wait for price to come into the context PD array and look for the entry model
— which can be pre-placed as a limit order and left to fill.

Faithful definitions, quoted from the ep-35 transcript
------------------------------------------------------

The context (always one of three) and the work split:

    > "we are always trading either in a monthly, weekly, or daily context ...
    > Let's say that we have a monthly context ... this monthly fair value gap ...
    > and this monthly order block ... we are likely continuing higher off of
    > that monthly order block and that monthly fair value gap ... we already have
    > our monthly context because the monthly context is that we are going higher
    > off of this discount [array] and we are targeting this premium [array] ...
    > In between this low to that high right there, that is where we want to get
    > involved."

    > "that is a process you would do on the weekend and then when you're truly
    > busy throughout the week the only thing you need to do is ... we're coming
    > into that context area so that pd ray and we want to look for our entry
    > model ... The hard work is done when you do have the time on the weekend to
    > look at the highest probability instruments."

The entry model (fractal — same at every context; this is the ep-23 ST model):

    > "the entry time frame ... that is where we want to have an ST [a first fair
    > value gap] ... then we want to have a second fair value gap coming off of a
    > discount array which is just your short term range ... so ST, new short term
    > range off of that ST, overlapping pd array — that is where we want to enter,
    > that is called your original entry ... you cover the intermediate term low
    > or the intermediate term high and you target around 1 to 2 RR."

    > Monthly context  -> 4-hour entry timeframe, re-entry on the Daily.
    > Weekly  context  -> 1-hour entry timeframe, re-entry on the 4-hour.
    > Daily   context  -> 1-hour entry timeframe.

Order placement / set-and-forget & risk:

    > "ideally you want to be entering on a Monday, Tuesday or a Wednesday ...
    > where we have news ... that's your ideal scenario."

    > "you don't execute on multiple pairs all at once. Be careful with your risk.
    > Maximum 2% risk at the time. So ... if you're risking 1% on every setup,
    > then there's only two setups that you can take at that time. If you're
    > already in a trade with 1% risk, then you can only take a maximum of one new
    > trade."

The re-entry opportunity (fractal, after the original entry resolves):

    > "the re-entry opportunity ... first the [entry-TF] opportunity already
    > happened ... you need to be at least break even, that's the minimum, then
    > you want to zoom out to the [next] time frame, enter on the overlapping part
    > of the short term range, cover short term low / short term high ... you can
    > target on the re-entry a 2R as well but you don't need to ... target that
    > monthly [context] high."

Break-even management (narrative — see ``break_even_when`` docstring):

    > "go break even when price has no reason to return based on a lot and flawed
    > ... LOT [last line of defense] ... FLOD [first line of defense]. ... when
    > you see it's close to your target and the LOT is just below your entry ...
    > that is when you go break even ... protect your capital."

Mechanical encoding
-------------------
This module is a thin, faithful *orchestration* over the existing atoz layers:

  * The context is a higher-timeframe PD array (an FVG / order block) we trade
    **from**, with the opposing HTF array as the target — the "low to high" band.
  * The entry model is reused verbatim from ``atoz.st_model.find_st_setups``
    ("ST + new FVG + overlapping entry, cover the ITL, target 1-to-2").
  * "Set and forget" = the entry is expressed as a resting **limit order** at the
    FVG edge (``OrderType.LIMIT``), so the busy trader can leave it to fill.

Pure functions over OHLC DataFrames (DatetimeIndex). No look-ahead — every setup
is anchored on bars at/below its confirming index.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import pandas as pd

from atoz.core.fvg import FVG, find_fvgs
from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Candles, Direction, Swing, SwingType, Zone
from atoz.st_model import STForm, STSetup, find_st_setups


# --------------------------------------------------------------------------- #
# Play-style configuration (the "unique trading plan that fits your schedule")
# --------------------------------------------------------------------------- #


class Context(Enum):
    """The higher-timeframe context the swing is taken in (ep 35).

    > "we are always trading either in a monthly, weekly, or daily context."
    """

    MONTHLY = "monthly"
    WEEKLY = "weekly"
    DAILY = "daily"


class OrderType(Enum):
    """How the entry is placed. Swing-around-a-job is set-and-forget = LIMIT."""

    LIMIT = "limit"     # rest the order at the FVG edge and leave it to fill.
    MARKET = "market"


# ep-35 mapping: each context has a fixed entry timeframe and a re-entry
# (zoom-out) timeframe. Quoted in the module docstring.
_CONTEXT_TIMEFRAMES = {
    Context.MONTHLY: ("4h", "1d"),   # original entry on 4H, re-entry on Daily.
    Context.WEEKLY:  ("1h", "4h"),   # original entry on 1H, re-entry on 4H.
    Context.DAILY:   ("1h", None),   # original entry on 1H.
}

# ep 35: "ideally you want to be entering on a Monday, Tuesday or a Wednesday".
# Monday=0 .. Sunday=6 (pandas Timestamp.weekday()).
IDEAL_ENTRY_WEEKDAYS = (0, 1, 2)


@dataclass
class SwingPlayStyle:
    """A faithful ep-35 swing play style for trading around a full-time job.

    Attributes mirror the choices the instructor says you must define for *your*
    schedule and personality:

    ``context``           monthly / weekly / daily (the HTF bias band).
    ``entry_timeframe``   the timeframe the entry model is executed on (derived
                          from ``context`` per ep 35, overridable).
    ``reentry_timeframe`` the zoom-out timeframe for the re-entry opportunity.
    ``order_type``        LIMIT for true set-and-forget (default).
    ``max_risk_pct``      "Maximum 2% risk at the time" (ep 35).
    ``risk_per_trade_pct``"if you're risking 1% on every setup" (ep 35).
    ``ideal_entry_weekdays`` Mon/Tue/Wed (ep 35).
    ``min_rr`` / ``target_rr`` "start off with a one to two ... just a 1 to 2"
                          (ep 35) — minimum 1.0, default target 2.0.
    """

    context: Context = Context.WEEKLY
    entry_timeframe: Optional[str] = None
    reentry_timeframe: Optional[str] = None
    order_type: OrderType = OrderType.LIMIT
    max_risk_pct: float = 2.0
    risk_per_trade_pct: float = 1.0
    ideal_entry_weekdays: tuple = IDEAL_ENTRY_WEEKDAYS
    min_rr: float = 1.0
    target_rr: float = 2.0

    def __post_init__(self) -> None:
        ef, rf = _CONTEXT_TIMEFRAMES[self.context]
        if self.entry_timeframe is None:
            self.entry_timeframe = ef
        if self.reentry_timeframe is None:
            self.reentry_timeframe = rf

    @property
    def max_concurrent_trades(self) -> int:
        """ep 35: max 2% total ÷ risk-per-trade -> how many setups at once."""
        if self.risk_per_trade_pct <= 0:
            return 0
        return int(self.max_risk_pct // self.risk_per_trade_pct)


# --------------------------------------------------------------------------- #
# The higher-timeframe context (the PD-array band we trade from -> to)
# --------------------------------------------------------------------------- #


@dataclass
class ContextBand:
    """The HTF context: a discount(/premium) PD array we trade *from* and the
    opposing array we target (ep 35 "this low to that high ... is where we want
    to get involved").
    """

    context: Context
    direction: Direction         # BULLISH: buy the discount array, target premium.
    array: Zone                  # the HTF PD array we get involved off of.
    target: float                # the opposing HTF array / context high / low.
    array_index: int             # bar (in the HTF df) the array confirms.

    @property
    def array_low(self) -> float:
        return self.array.bottom

    @property
    def array_high(self) -> float:
        return self.array.top


def find_context_bands(
    htf_df: pd.DataFrame,
    context=None,
    swings: Optional[List[Swing]] = None,
) -> List[ContextBand]:
    """Build the ep-35 context bands on a higher-timeframe DataFrame.

    A context is a HTF PD array (here, an FVG — "this monthly fair value gap")
    we trade *from*, targeting the opposing swing on the same HTF. A bullish
    context: a bullish HTF FVG (discount array) with a later/standing swing high
    above it as the target ("we are going higher off of this discount [array]
    and we are targeting this premium [array]").

    ``context`` may be a :class:`Context` enum value or a lower-timeframe
    DataFrame (ignored — provided for API convenience). When omitted or a
    DataFrame is passed, ``Context.DAILY`` is used as the label.

    Pure / no look-ahead: each band's target is the nearest opposing swing that
    already exists relative to the array's index is *not* required (the target is
    drawn liquidity that can be above to the right); we use the nearest swing
    extreme beyond the array in price.
    """
    # Normalize the context argument.
    if context is None or isinstance(context, pd.DataFrame):
        context_label: Context = Context.DAILY
    else:
        context_label = context  # type: ignore[assignment]

    if swings is None:
        swings = find_swings(htf_df)
    highs = swing_highs(swings)
    lows = swing_lows(swings)
    fvgs = find_fvgs(htf_df)

    out: List[ContextBand] = []
    for f in fvgs:
        if f.direction is Direction.BULLISH:
            # discount array -> target the nearest swing high ABOVE the array.
            tgts = [h.price for h in highs if h.price > f.top]
            if not tgts:
                continue
            out.append(
                ContextBand(
                    context=context_label, direction=Direction.BULLISH, array=f,
                    target=min(tgts), array_index=f.index,
                )
            )
        else:
            tgts = [l.price for l in lows if l.price < f.bottom]
            if not tgts:
                continue
            out.append(
                ContextBand(
                    context=context_label, direction=Direction.BEARISH, array=f,
                    target=max(tgts), array_index=f.index,
                )
            )
    out.sort(key=lambda b: b.array_index)
    return out


# --------------------------------------------------------------------------- #
# Set-and-forget limit-order setups (the deliverable)
# --------------------------------------------------------------------------- #


@dataclass
class LimitOrderSetup:
    """A pre-placed, set-and-forget swing setup (ep 35).

    Holds everything a busy trader needs to rest an order and walk away:

    ``order_type``   LIMIT (set-and-forget) or MARKET.
    ``entry_price``  the resting limit price (the entry-model FVG edge).
    ``stop_loss``    beneath the intermediate-term low / above the high.
    ``take_profit``  the 1-to-2 (or context-high) target.
    ``direction``    BULLISH / BEARISH.
    ``context_band`` the HTF context this setup belongs to.
    ``st_setup``     the reused ep-23 entry-model trigger.
    ``is_reentry``   False = original entry, True = the zoom-out re-entry.
    ``entry_time``   timestamp of the confirming entry-TF bar.
    ``ideal_day``    True if ``entry_time`` is Mon/Tue/Wed (ep 35).
    """

    order_type: OrderType
    direction: Direction
    entry_price: float
    stop_loss: float
    take_profit: float
    context_band: ContextBand
    st_setup: STSetup
    is_reentry: bool
    entry_time: pd.Timestamp
    ideal_day: bool

    @property
    def rr(self) -> float:
        risk = abs(self.entry_price - self.stop_loss)
        return abs(self.take_profit - self.entry_price) / risk if risk else 0.0


def _target_at_rr(entry: float, stop: float, rr: float, bullish: bool) -> float:
    """The price that gives ``rr`` reward-to-risk ("just a 1 to 2", ep 35)."""
    risk = abs(entry - stop)
    return entry + rr * risk if bullish else entry - rr * risk


def precompute_limit_setups(
    entry_df: pd.DataFrame,
    band: ContextBand,
    style: SwingPlayStyle,
    entry_times_align: bool = True,
) -> List[LimitOrderSetup]:
    """Pre-compute set-and-forget limit-order setups at a HTF context array (ep 35).

    This is the core deliverable: given the *context* (a HTF PD-array band found
    by :func:`find_context_bands`) and the trader's :class:`SwingPlayStyle`, find
    the entry-model triggers on the entry timeframe that line up with the context
    direction, and express each as a resting limit order ("set and forget").

    The entry model is reused verbatim from the ep-23 ST model
    (``find_st_setups``): ST + new FVG + overlapping entry, cover the
    intermediate-term low/high, target a 1-to-2. We then:

      * keep only entry-model triggers whose direction matches the HTF context;
      * keep only triggers whose entry zone is inside (or below, for longs) the
        context band — i.e. price "coming into that context area so that PD ray";
      * place the order at the FVG edge as a LIMIT (set-and-forget), the stop
        beneath the ITL, and the target at ``style.target_rr`` (default 1-to-2).

    ``entry_times_align`` keeps only setups whose confirming bar is on the
    instructor's ideal Monday/Tuesday/Wednesday (set False to keep all, with the
    ``ideal_day`` flag still set).
    """
    setups_st = find_st_setups(entry_df)
    out: List[LimitOrderSetup] = []
    bullish = band.direction is Direction.BULLISH

    for st in setups_st:
        if st.direction is not band.direction:
            continue
        # "coming into that context area / PD ray": the entry zone must sit at or
        # inside the context band on the entering side.
        if bullish and not (st.entry_price <= band.array_high):
            continue
        if not bullish and not (st.entry_price >= band.array_low):
            continue

        entry = st.entry_price
        stop = st.stop_loss
        if abs(entry - stop) < 1e-9:
            continue
        tp = _target_at_rr(entry, stop, style.target_rr, bullish)

        ts = entry_df.index[st.index]
        ideal = ts.weekday() in style.ideal_entry_weekdays
        if entry_times_align and not ideal:
            continue

        out.append(
            LimitOrderSetup(
                order_type=style.order_type, direction=band.direction,
                entry_price=float(entry), stop_loss=float(stop),
                take_profit=float(tp), context_band=band, st_setup=st,
                is_reentry=False, entry_time=ts, ideal_day=ideal,
            )
        )
    out.sort(key=lambda s: s.entry_time)
    return out


def find_reentry_setups(
    reentry_df: pd.DataFrame,
    band: ContextBand,
    style: SwingPlayStyle,
    after_time: Optional[pd.Timestamp] = None,
) -> List[LimitOrderSetup]:
    """The ep-35 re-entry opportunity on the zoom-out timeframe.

    > "the re-entry opportunity ... you need to be at least break even ... then
    > you want to zoom out to the [next] time frame, enter on the overlapping
    > part of the short term range, cover short term low / short term high ...
    > target that [context] high."

    Mechanically identical to :func:`precompute_limit_setups` but run on
    ``style.reentry_timeframe`` and, faithfully, the target is the **context
    high/low** (drawn liquidity) rather than a fixed 1-to-2 — the instructor says
    on the re-entry you can "just target that monthly high". ``after_time`` keeps
    only re-entries that occur after the original entry resolved.
    """
    if style.reentry_timeframe is None:
        return []
    setups_st = find_st_setups(reentry_df)
    out: List[LimitOrderSetup] = []
    bullish = band.direction is Direction.BULLISH

    for st in setups_st:
        if st.direction is not band.direction:
            continue
        ts = reentry_df.index[st.index]
        if after_time is not None and ts <= after_time:
            continue
        if bullish and not (st.entry_price <= band.array_high):
            continue
        if not bullish and not (st.entry_price >= band.array_low):
            continue

        entry = st.entry_price
        stop = st.stop_loss
        if abs(entry - stop) < 1e-9:
            continue
        # re-entry target = the context high / low (drawn liquidity).
        tp = band.target
        # guard: target must be on the profitable side of entry.
        if bullish and tp <= entry:
            continue
        if not bullish and tp >= entry:
            continue

        out.append(
            LimitOrderSetup(
                order_type=style.order_type, direction=band.direction,
                entry_price=float(entry), stop_loss=float(stop),
                take_profit=float(tp), context_band=band, st_setup=st,
                is_reentry=True, entry_time=ts,
                ideal_day=ts.weekday() in style.ideal_entry_weekdays,
            )
        )
    out.sort(key=lambda s: s.entry_time)
    return out


def break_even_when(setup: LimitOrderSetup) -> str:
    """ep-35 break-even rule (narrative — returned as guidance, not a signal).

    > "go break even when price has no reason to return based on a LOT and FLOD
    > ... when you see it's close to your target and the LOT [last line of
    > defense] is just below your entry ... that is when you go break even ...
    > protect your capital."

    This is a discretionary, structure-reading rule (it depends on the trader
    reading the *new* short-term ranges that form after entry and judging whether
    the last-line-of-defense has moved above the entry). It is **not** reducible
    to a single price threshold without re-deriving the post-entry short-term
    ranges, so we surface it as explicit text rather than a misleading proxy.
    """
    return (
        "Go break even once a new short-term range forms whose last-line-of-"
        "defense (LOT) sits beyond your entry and price is close to the drawn "
        "liquidity / target — i.e. price has no reason to return to entry "
        "(ep 35). FLOD is first line of defense, LOT is last."
    )

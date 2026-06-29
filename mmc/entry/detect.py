"""Entry detection inside a context area (transcript 11 — Entries using Order
Flow).

Two entry methods, both order-flow based and essentially the same thing on
different timeframes (transcript 11, ~2:05):

* **Sharp turn** (:func:`find_sharp_turns`) — an FVG **into** the context area
  (the manipulation / trap) followed by an FVG **out** of it (the real
  continuation). The FVGs need not overlap; the faster the turn, the better
  (~13:06). We enter on the FVG-out and place the stop above/below the most
  recent order flow lag.

* **Order flow lag entry** (:func:`find_order_flow_entries`) — two order flow
  lags on the entry timeframe: trade back into a premium/discount array and
  continue. Enter on the **second** lag's FVG, stop above/below that lag
  (~19:57).

All entries happen *inside* the context area: the "FVG in" first trades into the
boundary and the entry FVG must sit within the context (boundary -> target),
delegated to :meth:`ContextArea.contains_entry_zone` /
:meth:`ContextArea.price_in_boundary`.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

from mmc.core import (
    Direction,
    FairValueGap,
    OrderFlowLag,
    find_fvgs,
    find_order_flow_lags,
    find_swings,
    mark_mitigation,
)
from mmc.context import ContextArea

from .signal import Entry, make_stop_loss, make_take_profit

# A sharp turn is "fast" when the FVG-out forms within this many bars of the
# FVG-in (transcript 11, ~13:06 — "the faster it happens, the better").
FAST_SHARP_TURN_BARS = 6


def find_sharp_turns(
    context_area: ContextArea,
    entry_df: pd.DataFrame,
    rr: float = 2.0,
    fast_threshold: int = FAST_SHARP_TURN_BARS,
) -> List[Entry]:
    """Detect FVG-in-then-FVG-out sharp turns inside ``context_area``.

    Walks the entry-timeframe FVGs. The **FVG in** is an *opposing*-polarity FVG
    (the trap: it pushes against the context direction, into the boundary). The
    **FVG out** is a *same*-polarity FVG that forms after it and lies inside the
    context area — that is the FVG we enter on. The stop sits above/below the
    most recent order flow lag (the FVG-out's lag).
    """
    swings = find_swings(entry_df)
    fvgs = find_fvgs(entry_df)
    mark_mitigation(entry_df, fvgs)
    lags = find_order_flow_lags(swings, fvgs)

    ctx_dir = context_area.direction
    in_dir = ctx_dir.opposite  # the trap FVG goes against the context direction

    out: List[Entry] = []
    for fvg_in in fvgs:
        if fvg_in.direction is not in_dir:
            continue
        # The trap must trade into the boundary (a "sting into the context FVG").
        if not _touches_boundary(context_area, fvg_in):
            continue
        # The FVG out: a same-direction FVG forming *after* the trap, in context.
        fvg_out = _first_continuation_fvg(fvgs, fvg_in, ctx_dir, context_area)
        if fvg_out is None:
            continue
        lag = _lag_for(lags, fvg_out)
        if lag is None:
            continue
        entry = _build_entry(
            context_area,
            fvg_out,
            lag,
            entry_type="sharp_turn",
            rr=rr,
        )
        bars = fvg_out.index - fvg_in.index
        entry.bars_to_turn = bars
        entry.fast = bars <= fast_threshold
        out.append(entry)
    return out


def find_order_flow_entries(
    context_area: ContextArea,
    entry_df: pd.DataFrame,
    rr: float = 2.0,
) -> List[Entry]:
    """Detect two-order-flow-lag entries inside ``context_area``.

    Two same-direction order flow lags in the context direction: the first is
    the retrace back into the array, the second is the continuation we enter on.
    We enter on the **second** lag's FVG and stop above/below that lag
    (transcript 11, ~19:57).
    """
    swings = find_swings(entry_df)
    fvgs = find_fvgs(entry_df)
    mark_mitigation(entry_df, fvgs)
    lags = find_order_flow_lags(swings, fvgs)

    ctx_dir = context_area.direction
    # Lags in the context direction whose FVG sits inside the context area.
    in_ctx = [
        lag
        for lag in lags
        if lag.direction is ctx_dir
        and context_area.contains_entry_zone(lag.fvg)
    ]
    in_ctx.sort(key=lambda lg: lg.index)

    out: List[Entry] = []
    # Need at least two lags; enter on the second of each consecutive pair.
    for first, second in zip(in_ctx, in_ctx[1:]):
        entry = _build_entry(
            context_area,
            second.fvg,
            second,
            entry_type="order_flow",
            rr=rr,
        )
        out.append(entry)
    return out


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #


def _touches_boundary(context_area: ContextArea, fvg: FairValueGap) -> bool:
    """True if the FVG overlaps the context boundary band (the trap stings into
    the context FVG / boundary)."""
    b = context_area.boundary
    return fvg.top >= b.bottom and fvg.bottom <= b.top


def _first_continuation_fvg(
    fvgs: List[FairValueGap],
    fvg_in: FairValueGap,
    ctx_dir: Direction,
    context_area: ContextArea,
) -> Optional[FairValueGap]:
    """The first same-direction FVG after ``fvg_in`` that sits inside the context
    area and *clear of the boundary band* — the "fair value gap **out** of the
    context area" we enter on (transcript 11, ~2:17). Requiring it to clear the
    boundary distinguishes the continuation FVG from gaps still inside the
    boundary sting."""
    boundary = context_area.boundary
    for f in fvgs:
        if f.index <= fvg_in.index:
            continue
        if f.direction is not ctx_dir:
            continue
        if not context_area.contains_entry_zone(f):
            continue
        # "Out of" the context boundary: a bearish continuation sits fully below
        # the boundary bottom, a bullish one fully above the boundary top.
        if ctx_dir is Direction.BEARISH and f.top > boundary.bottom:
            continue
        if ctx_dir is Direction.BULLISH and f.bottom < boundary.top:
            continue
        return f
    return None


def _lag_for(
    lags: List[OrderFlowLag], fvg: FairValueGap
) -> Optional[OrderFlowLag]:
    """The order flow lag whose FVG is ``fvg`` (the most recent lag at entry)."""
    for lag in lags:
        if lag.fvg is fvg:
            return lag
    return None


def _build_entry(
    context_area: ContextArea,
    fvg: FairValueGap,
    lag: OrderFlowLag,
    entry_type: str,
    rr: float,
) -> Entry:
    """Assemble an :class:`Entry` from the entry FVG and its anchoring lag."""
    direction = context_area.direction
    entry_price = fvg.top if direction is Direction.BEARISH else fvg.bottom
    stop_loss = make_stop_loss(lag, direction)
    take_profit = make_take_profit(entry_price, stop_loss, rr=rr)
    return Entry(
        direction=direction,
        entry_zone=fvg,
        stop_loss=stop_loss,
        take_profit=take_profit,
        context=context_area,
        entry_type=entry_type,
        index=fvg.c3_index,
        lag=lag,
        rr=rr,
    )

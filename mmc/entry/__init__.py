"""MMC entry layer (transcript 11 — Entries using Order Flow).

**Entries are the easy part**: the hard work (direction, narrative, context) is
done on the higher timeframe. Entries always happen **inside a context area**
(a market maker model) and are all about **fair value gaps** (transcript 11,
~1:18 / ~1:54).

Two methods, both order-flow based and essentially the same thing on different
timeframes — pick one per plan (~2:05 / ~20:22):

* **Sharp turn** — FVG *in* to the context (the trap) -> FVG *out* of it (the
  continuation). Faster = better.
* **Order flow lag entry** — two order flow lags on the entry timeframe; enter on
  the second lag's FVG.

Trade management (~24:32): stop loss above/below the most recent order flow lag;
target a **1:2 RR** ideally within the context area; break even when there's no
reason to return based on order flow. Time-frame alignment has a baseline /
minimum (you may go higher, never lower).

This layer sits on ``mmc.core`` + ``mmc.context`` + ``mmc.timing`` and never
re-derives FVGs / swings / lags / context areas / kill zones.

Public API
----------
``Entry``
    The trade-signal dataclass (direction, entry FVG, SL, TP, RR, context, ...).
``find_entries(context_area, entry_df, entry_type=..., killzone=None, rr=2.0)``
    Top-level entry finder; optionally gated by a kill zone.
``find_sharp_turns`` / ``find_order_flow_entries``
    The two per-method detectors.
``make_stop_loss`` / ``make_take_profit`` / ``should_move_to_breakeven``
    Trade-management helpers.
``BASELINE_SHARP_TURN`` / ``BASELINE_ORDER_FLOW`` / ``is_valid_alignment``
    Time-frame alignment baselines and validator.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

from mmc.context import ContextArea
from mmc.timing import in_killzone

from .alignment import (
    BASELINE_ORDER_FLOW,
    BASELINE_SHARP_TURN,
    baseline_entry_tf,
    is_valid_alignment,
)
from .detect import find_order_flow_entries, find_sharp_turns
from .signal import (
    Entry,
    make_stop_loss,
    make_take_profit,
    should_move_to_breakeven,
)


def find_entries(
    context_area: ContextArea,
    entry_df: pd.DataFrame,
    entry_type: str = "sharp_turn",
    killzone: Optional[str] = None,
    rr: float = 2.0,
) -> List[Entry]:
    """Find entries inside ``context_area`` on the entry-timeframe ``entry_df``.

    ``entry_type`` selects the method: ``"sharp_turn"`` (FVG in -> FVG out) or
    ``"order_flow"`` (two order flow lags).

    When ``killzone`` is supplied (``"forex"`` / ``"index"`` / an
    :class:`~mmc.timing.Instrument`), entries are gated by
    :func:`mmc.timing.in_killzone` on the entry bar's timestamp — only entries
    whose confirming bar falls inside the lower-timeframe kill zone are kept
    (transcript 11, ~3:34 — lower-timeframe time can gate entries; most relevant
    at 15m and below).
    """
    if entry_type == "sharp_turn":
        entries = find_sharp_turns(context_area, entry_df, rr=rr)
    elif entry_type == "order_flow":
        entries = find_order_flow_entries(context_area, entry_df, rr=rr)
    else:
        raise ValueError(
            f"unknown entry_type {entry_type!r}; expected 'sharp_turn' or 'order_flow'"
        )

    if killzone is not None:
        entries = [e for e in entries if _bar_in_killzone(entry_df, e.index, killzone)]
    return entries


def _bar_in_killzone(entry_df: pd.DataFrame, index: int, killzone: str) -> bool:
    """Is the bar at integer position ``index`` inside the kill zone?"""
    timestamp = entry_df.index[index]
    return in_killzone(timestamp, instrument=killzone)


__all__ = [
    # signal + trade management
    "Entry",
    "make_stop_loss",
    "make_take_profit",
    "should_move_to_breakeven",
    # detection
    "find_entries",
    "find_sharp_turns",
    "find_order_flow_entries",
    # alignment
    "BASELINE_SHARP_TURN",
    "BASELINE_ORDER_FLOW",
    "baseline_entry_tf",
    "is_valid_alignment",
]

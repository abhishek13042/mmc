"""Time-frame alignment — the baseline / minimum entry timeframe per context
timeframe (transcript 11, ~10:34–11:53).

The closer the context timeframe and the entry timeframe are, the **less**
confirmation you need. The transcript gives a *baseline* (a minimum entry
timeframe) for each context timeframe, split by entry method:

Sharp turn (transcript 11, ~10:45):
    monthly ctx -> daily, weekly -> 4H, daily -> 1H, 4H -> 15m, 1H -> 5m,
    15m -> 1m. (15m is the lowest context area.)

Order flow (transcript 11, ~11:14):
    monthly -> 4H, weekly -> 1H, daily -> 15m, 4H -> 5m, 1H -> 1m, 15m -> 1m.

These are **minimums**: you may go *higher* (closer to the context TF, more
confirmation per candle) but never *lower* (transcript 11, ~11:28 — "these are
the minimums, don't go below it... you can go up, yes; we cannot go down").

Only the timeframes the core :class:`~mmc.core.Timeframe` enum supports
(M5..D1) are modelled here; monthly/weekly/1m from the transcript fall outside
the enum and so are represented by the closest supported baseline (daily ctx
and the M5/M15 minimums) — see the mappings below.
"""

from __future__ import annotations

from mmc.core import Timeframe

# Context timeframe -> minimum (baseline) entry timeframe for a SHARP TURN.
# (transcript 11, ~10:45). Limited to the supported Timeframe enum (M5..D1).
BASELINE_SHARP_TURN: dict[Timeframe, Timeframe] = {
    Timeframe.D1: Timeframe.H1,    # daily ctx -> 1H sharp turn
    Timeframe.H4: Timeframe.M15,   # 4H ctx -> 15m sharp turn
    Timeframe.H1: Timeframe.M5,    # 1H ctx -> 5m sharp turn
    Timeframe.M15: Timeframe.M5,   # 15m ctx -> 1m (clamped to M5 lowest supported)
}

# Context timeframe -> minimum (baseline) entry timeframe for an ORDER FLOW entry.
# (transcript 11, ~11:14). Limited to the supported Timeframe enum (M5..D1).
BASELINE_ORDER_FLOW: dict[Timeframe, Timeframe] = {
    Timeframe.D1: Timeframe.M15,   # daily ctx -> 15m order flow
    Timeframe.H4: Timeframe.M5,    # 4H ctx -> 5m order flow
    Timeframe.H1: Timeframe.M5,    # 1H ctx -> 1m (clamped to M5 lowest supported)
    Timeframe.M15: Timeframe.M5,   # 15m ctx -> 1m (clamped to M5 lowest supported)
}


def baseline_entry_tf(context_tf: Timeframe, entry_type: str = "sharp_turn") -> Timeframe:
    """Return the *minimum* (baseline) entry timeframe for ``context_tf``.

    ``entry_type`` is ``"sharp_turn"`` or ``"order_flow"``. Raises if the context
    timeframe has no defined baseline (e.g. M5 — "5m context areas: don't,
    stay at 15m or above", transcript 11 ~11:02).
    """
    table = _table_for(entry_type)
    if context_tf not in table:
        raise ValueError(
            f"no baseline entry timeframe for context {context_tf.name!r} "
            f"({entry_type}); the lowest supported context area is 15m"
        )
    return table[context_tf]


def is_valid_alignment(
    context_tf: Timeframe,
    entry_tf: Timeframe,
    entry_type: str = "sharp_turn",
) -> bool:
    """Is ``entry_tf`` a valid entry timeframe for ``context_tf``?

    Valid means: the entry timeframe is **at or above the baseline** (you may go
    higher/closer to the context TF, never lower) **and not above** the context
    timeframe itself (an entry timeframe is always <= the context timeframe).
    (transcript 11, ~11:28.)
    """
    try:
        baseline = baseline_entry_tf(context_tf, entry_type)
    except ValueError:
        return False
    # entry TF may not be below the baseline (never go lower) ...
    if entry_tf.minutes < baseline.minutes:
        return False
    # ... and may not exceed the context TF (entries live on a lower/equal TF).
    if entry_tf.minutes > context_tf.minutes:
        return False
    return True


def _table_for(entry_type: str) -> dict[Timeframe, Timeframe]:
    if entry_type == "sharp_turn":
        return BASELINE_SHARP_TURN
    if entry_type == "order_flow":
        return BASELINE_ORDER_FLOW
    raise ValueError(
        f"unknown entry_type {entry_type!r}; expected 'sharp_turn' or 'order_flow'"
    )

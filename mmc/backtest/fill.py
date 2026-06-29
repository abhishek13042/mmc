"""The fill model — the deterministic, event-driven core of the simulator.

Given a single :class:`~mmc.entry.Entry` and the OHLC bars **after** its
confirming index, :func:`simulate_entry` reproduces what a resting limit order at
the entry price would have experienced:

1. **Limit fill.** We wait, bar by bar, until price *trades into* the entry zone
   (transcript 10/11 — "as soon as we trade back into that fair value gap we drop
   to the lower timeframe"). The fill price is the entry signal's ``entry_price``
   (the near FVG edge in the trade's favour); the limit is considered touched
   when the bar's range reaches it. If no bar ever touches the zone within the
   simulated window the trade is ``NO_FILL``.

2. **Outcome resolution.** From the fill bar onward we walk forward checking each
   bar's range against the stop loss and take profit, respecting direction
   polarity (a bearish trade stops *above*, targets *below*; bullish is the
   mirror). When **both** levels fall inside the same bar we cannot know the
   intrabar path, so we resolve **conservatively** — assume the **stop hit
   first** — and flag the trade ``ambiguous`` (transcript 11's probability ladder
   demands more from price for the further level, so we never hand ourselves the
   benefit of the doubt).

3. **Timeout.** An optional ``max_hold`` caps how many bars (counted from the
   fill bar) a position may stay open; on expiry we exit at that bar's close and
   record the partial ``R`` (transcript 11, ~24:32 — manage out when there's no
   reason to stay).

P/L is reported in ``R`` multiples where ``R = |entry - stop|``.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from mmc.core import Direction
from mmc.entry import Entry

from .result import Outcome, Trade


def _r_multiple(entry: Entry, exit_price: float) -> float:
    """Realised R for closing a position at ``exit_price``.

    ``+`` when the exit is in the trade's favour relative to entry, ``-`` when
    against. One ``R`` equals the entry-to-stop distance.
    """
    risk = entry.risk
    if risk == 0:
        return 0.0
    move = (exit_price - entry.entry_price) * entry.direction.sign
    return move / risk


def simulate_entry(
    entry: Entry,
    df: pd.DataFrame,
    *,
    max_hold: Optional[int] = None,
) -> Trade:
    """Simulate a single ``entry`` against ``df`` and return a :class:`Trade`.

    Bars are addressed by integer position (``df.iloc``), matching the rest of
    the library. Only bars **after** ``entry.index`` are eligible — the entry is
    confirmed on bar ``entry.index``, so a fill can occur on ``entry.index + 1``
    at the earliest.

    Parameters
    ----------
    entry:
        The trade signal. ``entry.entry_price`` is the limit price, ``stop_loss``
        / ``take_profit`` are absolute price levels.
    df:
        The entry-timeframe OHLC DataFrame the signal was generated on.
    max_hold:
        Optional maximum number of bars to hold *after the fill bar* before
        force-closing at the close (``None`` = hold until SL/TP or data runs out).
    """
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    n = len(df)

    direction = entry.direction
    entry_price = entry.entry_price
    stop = entry.stop_loss
    target = entry.take_profit
    bullish = direction is Direction.BULLISH

    start = entry.index + 1

    # ----- 1. Limit fill: wait for price to trade into the entry price. ----- #
    fill_index: Optional[int] = None
    for j in range(start, n):
        # A resting limit at ``entry_price`` is touched when the bar's range
        # reaches it: a bullish (discount) entry fills when the low drops to it;
        # a bearish (premium) entry fills when the high rises to it.
        if bullish and lows[j] <= entry_price:
            fill_index = j
            break
        if not bullish and highs[j] >= entry_price:
            fill_index = j
            break

    if fill_index is None:
        return Trade(entry=entry, outcome=Outcome.NO_FILL)

    # ----- 2. Resolve outcome bar-by-bar from the fill bar onward. ---------- #
    # The fill bar itself can also hit SL/TP (price kept moving after the touch).
    hold_limit = n - 1 if max_hold is None else min(n - 1, fill_index + max_hold)

    for j in range(fill_index, hold_limit + 1):
        hi = highs[j]
        lo = lows[j]
        if bullish:
            hit_stop = lo <= stop
            hit_target = hi >= target
        else:
            hit_stop = hi >= stop
            hit_target = lo <= target

        if hit_stop and hit_target:
            # Ambiguous bar — resolve conservatively (assume stop first).
            return Trade(
                entry=entry,
                outcome=Outcome.LOSS,
                fill_price=entry_price,
                fill_index=fill_index,
                exit_price=stop,
                exit_index=j,
                r_multiple=_r_multiple(entry, stop),
                ambiguous=True,
            )
        if hit_stop:
            return Trade(
                entry=entry,
                outcome=Outcome.LOSS,
                fill_price=entry_price,
                fill_index=fill_index,
                exit_price=stop,
                exit_index=j,
                r_multiple=_r_multiple(entry, stop),
            )
        if hit_target:
            return Trade(
                entry=entry,
                outcome=Outcome.WIN,
                fill_price=entry_price,
                fill_index=fill_index,
                exit_price=target,
                exit_index=j,
                r_multiple=_r_multiple(entry, target),
            )

    # ----- 3. Neither level hit within the window -> timeout at close. ------ #
    exit_idx = hold_limit
    exit_price = float(closes[exit_idx])
    return Trade(
        entry=entry,
        outcome=Outcome.TIMEOUT,
        fill_price=entry_price,
        fill_index=fill_index,
        exit_price=exit_price,
        exit_index=exit_idx,
        r_multiple=_r_multiple(entry, exit_price),
    )

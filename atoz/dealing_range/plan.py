"""Dealing-range trading plan (A-Z Guide ep 21).

Ep 21 wraps the dealing range into an objective, step-by-step plan:

1. **Context / narrative (higher time frame).**
   > "narrative and context starts on the higher time frame ... we are moving
   > from a daily fair value gap (a premium array) the price will now seek a new
   > discount array because price moves from premium to discount ... in between
   > this premium array and that discount array ... is where we want to look for
   > 15 minute dealing ranges."
   So a higher-TF *premium array* (e.g. a daily FVG just tapped) sets a bearish
   draw toward the next *discount array* (the target). The zone between them is
   where lower-TF dealing ranges are valid.

2. **Entry pattern = dealing range (lower time frame).**
   > "we are only trading dealing ranges ... we want to enter at the low of that
   > dealing range (bearish) ... place your stop above the dealing range high ...
   > target that opposing daily discount array."

3. **R filter.**
   > "this is 0.6 rr is that worth it no at least a minimum of one to one rr ...
   > so that invalidates the idea."  → drop setups below ``min_rr``.

This module composes the ep-21 dealing range with a supplied higher-TF
target/draw to produce concrete trade setups (entry / stop / target / R).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from atoz.core import Direction, Swing
from .range import DealingRange, find_dealing_ranges


@dataclass
class DealingRangeTrade:
    """A concrete ep-21 dealing-range setup.

    - ``dealing_range`` : the lower-TF dealing range used as the entry pattern.
    - ``entry`` / ``stop`` / ``target`` : the three prices.
    - ``rr`` : reward-to-risk = |target-entry| / |entry-stop|.
    """

    dealing_range: DealingRange
    entry: float
    stop: float
    target: float
    direction: Direction

    @property
    def risk(self) -> float:
        return abs(self.entry - self.stop)

    @property
    def reward(self) -> float:
        return abs(self.target - self.entry)

    @property
    def rr(self) -> float:
        return self.reward / self.risk if self.risk else 0.0


def build_trades(
    df: pd.DataFrame,
    draw_on_liquidity: float,
    context_top: float,
    context_bottom: float,
    direction: Direction,
    swings: Optional[List[Swing]] = None,
    require_fvg: bool = False,
    min_rr: float = 1.0,
) -> List[DealingRangeTrade]:
    """Build ep-21 dealing-range trades toward ``draw_on_liquidity``.

    - ``draw_on_liquidity`` : the higher-TF target (the opposing daily PD array,
      e.g. the daily discount swing low for a bearish draw).
    - ``context_top`` / ``context_bottom`` : the higher-TF premium↔discount band
      ("in between this premium array and that discount array") within which
      lower-TF dealing ranges are valid; ranges fully outside are ignored.
    - ``direction`` : the higher-TF draw direction (BEARISH = premium→discount).
    - ``require_fvg`` : apply the ep-21 FVG rule to dealing ranges.
    - ``min_rr`` : drop setups whose R is below this (ep 21 "at least 1:1").

    Only dealing ranges matching ``direction`` are taken; entry = dealing-range
    extreme, stop = opposite extreme, target = ``draw_on_liquidity``.
    """
    ranges = find_dealing_ranges(df, swings=swings, require_fvg=require_fvg)
    trades: List[DealingRangeTrade] = []

    for dr in ranges:
        if dr.direction is not direction:
            continue
        # Must sit inside the higher-TF context band.
        if dr.high < context_bottom or dr.low > context_top:
            continue

        trade = DealingRangeTrade(
            dealing_range=dr,
            entry=dr.entry,
            stop=dr.stop,
            target=draw_on_liquidity,
            direction=dr.direction,
        )
        # Target must be on the correct side of entry for the draw.
        if direction is Direction.BEARISH and trade.target >= trade.entry:
            continue
        if direction is Direction.BULLISH and trade.target <= trade.entry:
            continue
        if trade.rr < min_rr:
            continue
        trades.append(trade)

    return trades

"""The "most accurate entry pattern" — A-Z Guide ep 22 (Trading Plan).

This episode answers "how far can price retrace before we continue?" with a
single mechanical rule, and gives the Fibonacci/OTE scaffold and the stop-loss
placement that the ST model (ep 23) then reuses.

Faithful definitions, quoted from the ep-22 transcript
------------------------------------------------------

The range / dealing range (and the Fib):

    > "what is the range that is causing that move higher? ... it is that range,
    > this swing low towards that swing high right there. That is aka your
    > dealing range ... your new intermediate term range. ... draw a Fibonacci
    > from that swing low to that swing high ... 1 and 0. 1 is a swing low, 0 is
    > a swing high ... 0.79, 0.705, 0.618, 0.5 ... 0.705 is your OTE level. 0.5
    > is your equilibrium. Everything above it is in premium, everything below
    > it is in discount."

The entry rule (THE pattern):

    > "use this OTE as a guideline but there's something else that is more
    > important ... overlapping PD arrays ... close to your equilibrium you will
    > likely have overlapping PD arrays ... The strongest magnet before we
    > expand further is the overlapping PD array spot. ... Enter on the first
    > place where we have overlapping PD rays — an overlapping PD ray is a fair
    > value gap overlapping with another discount array (a breaker / order block
    > / mitigation block). ... Enter on the first overlapping PD ray. ... it
    > doesn't have to be in discount, doesn't have to be at your OTE level
    > because we will not always reach that OTE level."

    > "I am entering on the fair value gaps because I love fair value gaps and
    > that is exactly what makes it mechanical. what could also make it
    > mechanical is you enter on the exact spot where we are overlapping with the
    > PD ray."  (two faithful entry-price choices.)

Stop-loss placement:

    > "what you're going to cover here is the intermediate term low ... beneath
    > that intermediate term low. ... rather than being greedy and finding the
    > best RR ... why not give your stop loss some room to breathe, putting it at
    > the breaker or even putting it at the intermediate term low, covering the
    > bodies of the candles."

Targets:

    > "the first target being this high, second target being that high ... the
    > ultimate target right there" (the premium arrays / draw on liquidity).

Mechanical encoding (long; bearish is the mirror)
-------------------------------------------------
Given the dealing range (swing low L -> swing high H that caused the expansion):

  * Fibonacci levels from 1 (=L) to 0 (=H): 0.5 (equilibrium), 0.618, 0.705
    (OTE), 0.79. premium > 0.5 > discount.
  * Entry  = the FIRST overlapping PD array price retraces into = the first
    fair value gap that overlaps another discount array (block). Entry price is
    either the FVG discount edge (``EntryStyle.FVG``) or the overlap-zone edge
    (``EntryStyle.OVERLAP``).
  * Stop   = beneath the intermediate-term low (``StopStyle.ITL``) or at the
    breaker/overlap block (``StopStyle.BREAKER``) — bodies covered.
  * Target = the swing highs above (first, second, ultimate).

Pure functions over an OHLC DataFrame, no look-ahead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import pandas as pd

from atoz.core.fvg import FVG, find_fvgs
from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Candles, Direction, Swing, SwingType, Zone

# ep-22 Fibonacci settings, named exactly as in the transcript.
FIB_LEVELS = (1.0, 0.79, 0.705, 0.618, 0.5, 0.0)
OTE = 0.705
EQUILIBRIUM = 0.5


class EntryStyle(Enum):
    """Two faithful ep-22 entry-price choices (pick one and stick to it)."""

    FVG = "fvg"           # "enter on the fair value gaps" — the FVG discount edge.
    OVERLAP = "overlap"   # "enter on the exact spot where we are overlapping".


class StopStyle(Enum):
    """Two faithful ep-22 stop-placement choices ("give it room to breathe")."""

    ITL = "intermediate_term_low"   # beneath the intermediate-term low/high.
    BREAKER = "breaker"             # at the overlapping breaker/block.


@dataclass
class STEntry:
    """An ep-22 "most accurate" overlapping-PD-array entry.

    Returned with the four things the transcript names: ``direction``,
    ``entry_price``, ``stop_loss``, ``take_profit`` (+ a list of further targets),
    and ``index`` (the bar the trigger FVG confirms).
    """

    direction: Direction
    entry_price: float
    stop_loss: float
    take_profit: float           # first target
    targets: List[float]         # first, second, ultimate (draw on liquidity)
    overlap_fvg: FVG             # the fair value gap that triggered the entry
    overlap_block: Zone          # the discount array it overlaps (breaker/OB/MB)
    dealing_range: "DealingRange"
    index: int                   # overlap_fvg.c3_index

    @property
    def rr(self) -> float:
        risk = abs(self.entry_price - self.stop_loss)
        return abs(self.take_profit - self.entry_price) / risk if risk else 0.0


@dataclass
class DealingRange:
    """The swing-low -> swing-high range that caused the expansion (ep 22).

    Provides the Fibonacci / OTE / equilibrium levels the episode defines.
    """

    low: float
    high: float
    low_index: int
    high_index: int
    direction: Direction          # BULLISH: low->high (longs); BEARISH: high->low

    @property
    def equilibrium(self) -> float:
        return (self.low + self.high) / 2.0

    def fib(self, level: float) -> float:
        """Price at a Fib ``level`` where 1.0 == swing low, 0.0 == swing high
        (the exact ep-22 convention)."""
        # for BULLISH: 1 -> low, 0 -> high
        if self.direction is Direction.BULLISH:
            return self.high - level * (self.high - self.low)
        # for BEARISH the range is high(1) -> low(0)
        return self.low + level * (self.high - self.low)

    @property
    def ote(self) -> float:
        return self.fib(OTE)

    def is_discount(self, price: float) -> bool:
        """Below equilibrium (ep 22: 'everything below it is in discount')."""
        if self.direction is Direction.BULLISH:
            return price <= self.equilibrium
        return price >= self.equilibrium


# --------------------------------------------------------------------------- #
# shared helpers (reused by the ST model, ep 23)
# --------------------------------------------------------------------------- #


def _intermediate_term_low_high(
    anchor: Swing, lows: List[Swing], highs: List[Swing], bullish: bool
) -> float:
    """The intermediate-term low (for longs) / high (for shorts) to stop beyond.

    ep 22/23: stop goes "beneath the intermediate term low ... covering the
    bodies". We use the anchor swing's price as that intermediate-term level.
    """
    return anchor.price


def _draw_targets(
    highs: List[Swing], lows: List[Swing], from_index: int, entry: float, bullish: bool
) -> Optional[float]:
    """First target = next swing high above the entry (for longs); the draw on
    liquidity (ep 22 'first target being this high')."""
    if bullish:
        cands = sorted((h.price for h in highs if h.index < from_index and h.price > entry))
        return cands[0] if cands else None
    cands = sorted((l.price for l in lows if l.index < from_index and l.price < entry), reverse=True)
    return cands[0] if cands else None


def _all_targets(
    highs: List[Swing], lows: List[Swing], from_index: int, entry: float, bullish: bool
) -> List[float]:
    """First, second, ... targets (the successive highs / draw on liquidity)."""
    if bullish:
        return sorted({h.price for h in highs if h.index < from_index and h.price > entry})
    return sorted({l.price for l in lows if l.index < from_index and l.price < entry}, reverse=True)


def build_dealing_range(low: Swing, high: Swing) -> DealingRange:
    """The expansion range: swing low -> swing high (ep 22 'dealing range')."""
    bullish = low.index < high.index
    return DealingRange(
        low=low.price, high=high.price,
        low_index=low.index, high_index=high.index,
        direction=Direction.BULLISH if bullish else Direction.BEARISH,
    )


def _overlaps_price_zone(a: Zone, b: Zone) -> bool:
    return a.bottom <= b.top and a.top >= b.bottom


def find_entry_patterns(
    df: pd.DataFrame,
    blocks: Optional[List[Zone]] = None,
    swings: Optional[List[Swing]] = None,
    entry_style: EntryStyle = EntryStyle.FVG,
    stop_style: StopStyle = StopStyle.ITL,
    retrace_window: int = 40,
) -> List[STEntry]:
    """Detect the ep-22 "most accurate" overlapping-PD-array entries.

    For each expansion (a swing low -> later swing high for longs), build the
    dealing range, then take the FIRST fair value gap, after the expansion, that
    overlaps another discount array (a block). That overlap is the entry; the
    intermediate-term low is the stop; the highs are the targets.

    ``blocks`` are the overlapping PD arrays (breaker / order block / mitigation
    block). If omitted, only FVG-on-FVG overlaps are considered (so the detector
    still runs without the blocks layer); pass ``find_all_blocks(df)`` for the
    full faithful behaviour.
    """
    c = Candles.of(df)
    if swings is None:
        swings = find_swings(df)
    fvgs = find_fvgs(df)
    highs = swing_highs(swings)
    lows = swing_lows(swings)

    overlap_zones: List[Zone] = list(blocks) if blocks else []

    out: List[STEntry] = []
    seen_fvg: set = set()

    for lo in lows:
        # the swing high that caused the expansion off this low (next high after it).
        hi = next((h for h in highs if h.index > lo.index and h.price > lo.price), None)
        if hi is None:
            continue
        dealing = build_dealing_range(lo, hi)
        bullish = True
        want = Direction.BULLISH

        # FIRST overlapping PD array (FVG overlapping a discount block) after the
        # expansion, within retrace_window bars of the swing high.
        trigger: Optional[FVG] = None
        overlap_block: Optional[Zone] = None
        for f in fvgs:
            if f.direction is not want:
                continue
            if f.index <= hi.index or f.index > hi.index + retrace_window:
                continue
            if f.c3_index in seen_fvg:
                continue
            # find an overlapping discount block of the same direction nearby.
            ob = next(
                (b for b in overlap_zones
                 if getattr(b, "direction", None) is want
                 and abs(b.index - f.index) <= retrace_window
                 and _overlaps_price_zone(f, b)),
                None,
            )
            # also allow FVG-on-FVG overlap when no block layer is supplied.
            if ob is None and not overlap_zones:
                ob = next(
                    (g for g in fvgs
                     if g is not f and g.direction is want
                     and abs(g.index - f.index) <= retrace_window
                     and _overlaps_price_zone(f, g)),
                    None,
                )
            if ob is not None:
                trigger, overlap_block = f, ob
                break

        if trigger is None or overlap_block is None:
            continue
        seen_fvg.add(trigger.c3_index)

        # entry price (two faithful styles).
        if entry_style is EntryStyle.FVG:
            entry = trigger.bottom            # FVG discount edge.
        else:
            entry = max(trigger.bottom, overlap_block.bottom)  # the overlap spot.

        # stop (two faithful styles), bodies covered.
        if stop_style is StopStyle.ITL:
            stop = lo.price                   # beneath the intermediate-term low.
        else:
            stop = overlap_block.bottom       # at the breaker/block.

        tgts = _all_targets(highs, lows, trigger.index, entry, bullish)
        if not tgts or abs(entry - stop) < 1e-9:
            continue

        out.append(
            STEntry(
                direction=want, entry_price=float(entry), stop_loss=float(stop),
                take_profit=float(tgts[0]), targets=[float(t) for t in tgts],
                overlap_fvg=trigger, overlap_block=overlap_block,
                dealing_range=dealing, index=trigger.c3_index,
            )
        )

    out.sort(key=lambda e: e.index)
    return out

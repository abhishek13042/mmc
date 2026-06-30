"""The ST (Sharp Turn) model — A-Z Guide ep 23 ("Market Structure Shift is BS").

The instructor argues the classic Market Structure Shift (MSS) is an unreliable,
secondary signal and that *fair value gaps tell the story*. The ST ("sharp turn")
model is his own reversal-entry pattern that does **not** require an MSS.

Faithful definitions, quoted from the ep-23 transcript
------------------------------------------------------

MSS recap (what we are replacing):

    > "when we come into a discount array ... the first and most recent swing
    > high ... if we trade back above that that is exactly a market structure
    > shift ... it is a market structure shift with a displacement ... above
    > that swing high we would need to see a displacement. ... A displacement is
    > a fair value gap. Fair value gap equals displacement."

The ST model — highest-probability pattern ("displacement, retracement,
displacement"):

    > "the only thing relevant is if we are having bullish fair value gaps
    > higher. if we have one bullish fair value gap higher and we trade back
    > into a discount array — that can either be the bullish fair value gap
    > itself or a breaker that's sitting right there — and then we have a new
    > bullish fair value gap higher. so that's two displacements in a row.
    > It's a mechanical: displacement, retracement, displacement. that exactly
    > is your highest probability entry pattern. what can you do after that —
    > you can use the concepts of the previous episode to get to an entry with
    > an overlapping PD array ... off of that breaker right there, covering that
    > low right there, and targeting the highs."

The ST model — advanced single-FVG entry (combine timeframes, enter *before* any
MSS):

    > "you can enter on the first bearish fair value gap right there. that right
    > there is exactly how you can enter without needing a market structure
    > shift ... we tap into [the HTF premium] right there ... the only thing we
    > need to see is a bearish fair value gap right there ... we don't trade
    > back into it but we have a new fair value gap to work with, so you would
    > enter on this fair value gap right there ... where's your stop loss —
    > above the potential intermediate term high, targeting the future drawn
    > liquidity."

Logic (why ST over MSS):

    > "if price is ran by some sort of algorithm ... they have huge orders ...
    > price will displace ... price will leave behind inefficiencies ... the
    > fair value gaps are the most important ... it is not that market structure
    > shift that's telling you a story."

Mechanical encoding (long; bearish is the mirror)
-------------------------------------------------
The ST model is anchored on a **discount array** (for longs). We faithfully model
that anchor as a bullish PD array zone (the swept swing-low region / a block /
the first FVG) that price has traded into. From there:

    HIGH-PROBABILITY (displacement → retracement → displacement):
      1. displacement-1 : a bullish FVG (displacement up).
      2. retracement     : price trades back DOWN into a discount array — either
                           into displacement-1's own FVG zone, or into a breaker
                           sitting there.
      3. displacement-2 : a *new* bullish FVG higher (the second displacement).
      -> entry  : the ep-22 overlapping-PD-array rule applied around the
                  retracement (the FVG / breaker overlap). We use the second
                  displacement FVG's discount edge as the mechanical entry.
      -> stop   : below the intermediate-term low (the swing-low anchor), bodies
                  covered (delegated to ep-22 ``stop_below_itl``).
      -> target : the highs / draw on liquidity above.

    ADVANCED (single FVG, no MSS):
      1. price taps an HTF discount array (anchor).
      2. one bullish FVG appears (displacement up) — NOT traded back into.
      3. a *new* bullish FVG higher -> enter on that FVG directly.
      -> stop below the potential intermediate-term low; target the highs.

Both forms share the invariant the instructor repeats: **no MSS is required** —
the second/new FVG is the trigger, "if bullish FVG, enter".

Pure functions over an OHLC DataFrame (no look-ahead: a pattern at displacement-2
only uses bars up to and including displacement-2's c3 candle).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pandas as pd

from atoz.core.fvg import FVG, find_fvgs
from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Candles, Direction, Swing, SwingType, Zone

from .entry_pattern import STEntry, _intermediate_term_low_high, _draw_targets


class STForm(Enum):
    """Which faithful ep-23 form produced the entry."""

    #: displacement → retracement → displacement (highest probability).
    DISPLACEMENT_RETRACEMENT_DISPLACEMENT = "displacement_retracement_displacement"
    #: single new FVG, entered before any MSS (combine-timeframes / "crazy early").
    SINGLE_FVG = "single_fvg"


@dataclass
class STSetup:
    """A detected ST (sharp turn) reversal entry (ep 23).

    Returns the exact things the transcript names: an entry price (off a fair
    value gap), a stop (above/below the potential intermediate-term high/low),
    and a take-profit (the future drawn liquidity / the highs).
    """

    direction: Direction
    form: STForm
    entry_price: float           # off a fair value gap (the trigger FVG)
    stop_loss: float             # beyond the intermediate-term high/low
    take_profit: float           # future drawn liquidity (highs/lows)
    displacement_1: FVG          # first displacement (None-equivalent: same as trigger for SINGLE_FVG)
    displacement_2: FVG          # the new FVG that triggers the entry
    anchor: Zone                 # the discount/premium array we tapped into
    index: int                   # bar the trigger FVG confirms (displacement_2.c3_index)

    @property
    def rr(self) -> float:
        risk = abs(self.entry_price - self.stop_loss)
        return abs(self.take_profit - self.entry_price) / risk if risk else 0.0


def _retraces_into(fvg: FVG, c: Candles, lo: int, hi: int) -> bool:
    """True if any candle in (lo, hi] trades back into ``fvg``'s price zone.

    Faithful to "we trade back into a discount array — that can either be the
    bullish fair value gap itself" (ep 23): for a bullish FVG, price dips back to
    touch/enter the gap (low <= fvg.top) after it formed.
    """
    for k in range(lo, min(hi, c.n - 1) + 1):
        if fvg.direction is Direction.BULLISH:
            if c.low[k] <= fvg.top:
                return True
        else:
            if c.high[k] >= fvg.bottom:
                return True
    return False


def find_st_setups(
    df: pd.DataFrame,
    swings: Optional[List[Swing]] = None,
    gap_window: int = 20,
    include_single_fvg: bool = True,
) -> List[STSetup]:
    """Detect ST-model sharp-turn entries (ep 23), both faithful forms.

    The anchor is a swept swing (a discount array for longs / premium for
    shorts). From it we look for the displacement→retracement→displacement
    sequence (and, if ``include_single_fvg``, the new-FVG single-trigger form).

    ``gap_window`` bounds how far apart the two displacements may be (the
    sequence must be "in a row").
    """
    c = Candles.of(df)
    if swings is None:
        swings = find_swings(df)
    fvgs = find_fvgs(df)
    highs = swing_highs(swings)
    lows = swing_lows(swings)

    out: List[STSetup] = []

    for sw in swings:
        bullish = sw.kind is SwingType.LOW
        want = Direction.BULLISH if bullish else Direction.BEARISH

        # anchor = the swept swing region (the discount/premium array we trade into).
        # find the bar that sweeps the swing (price taps the array).
        sweep_at = None
        for k in range(sw.index + 1, c.n):
            if bullish and c.low[k] < sw.price:
                sweep_at = k
                break
            if not bullish and c.high[k] > sw.price:
                sweep_at = k
                break
        if sweep_at is None:
            continue

        anchor = Zone(
            top=float(c.high[sw.index]) if bullish else float(c.high[sw.index]),
            bottom=float(c.low[sw.index]),
            index=sw.index,
            direction=want,
        )

        # displacement-1: first FVG of the right direction at/after the sweep.
        disp1 = next(
            (f for f in fvgs
             if f.direction is want and sweep_at <= f.index <= sweep_at + gap_window),
            None,
        )
        if disp1 is None:
            continue

        # displacement-2: a NEW FVG higher (for longs) after disp1, within window.
        disp2 = None
        for f in fvgs:
            if f.direction is not want:
                continue
            if f.index <= disp1.c3_index:
                continue
            if f.index > disp1.c3_index + gap_window:
                break
            # "new bullish fair value gap higher": disp2 is above disp1 for longs.
            if bullish and f.bottom >= disp1.bottom:
                disp2 = f
                break
            if not bullish and f.top <= disp1.top:
                disp2 = f
                break

        if disp2 is None:
            continue

        # --- HIGH-PROBABILITY form: displacement -> retracement -> displacement
        # retracement: price trades back into disp1's discount array in the
        # interval BETWEEN the two displacements (ep 23 "we trade back into a
        # discount array ... and then we have a new bullish fair value gap").
        retraced = _retraces_into(disp1, c, disp1.c3_index, disp2.c1_index)

        if retraced:
            itl = _intermediate_term_low_high(sw, lows, highs, bullish)
            entry = disp2.bottom if bullish else disp2.top
            stop = itl
            tp = _draw_targets(highs, lows, disp2.index, entry, bullish)
            if tp is not None and abs(entry - stop) > 1e-9:
                out.append(
                    STSetup(
                        direction=want,
                        form=STForm.DISPLACEMENT_RETRACEMENT_DISPLACEMENT,
                        entry_price=float(entry), stop_loss=float(stop),
                        take_profit=float(tp), displacement_1=disp1,
                        displacement_2=disp2, anchor=anchor,
                        index=disp2.c3_index,
                    )
                )
                continue  # prefer the high-probability form for this swing

        # --- ADVANCED single-FVG form: NOT traded back into disp1, new FVG -> enter.
        if include_single_fvg and not retraced:
            itl = _intermediate_term_low_high(sw, lows, highs, bullish)
            entry = disp2.bottom if bullish else disp2.top
            stop = itl
            tp = _draw_targets(highs, lows, disp2.index, entry, bullish)
            if tp is not None and abs(entry - stop) > 1e-9:
                out.append(
                    STSetup(
                        direction=want, form=STForm.SINGLE_FVG,
                        entry_price=float(entry), stop_loss=float(stop),
                        take_profit=float(tp), displacement_1=disp1,
                        displacement_2=disp2, anchor=anchor,
                        index=disp2.c3_index,
                    )
                )

    out.sort(key=lambda s: s.index)
    return out

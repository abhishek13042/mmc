"""Liquidity sweeps (turtle soups) vs liquidity runs (transcript 08).

Liquidity is swing points: a swing high is sell-side liquidity, a swing low is
buy-side liquidity (transcript 08 / transcript 01). When price trades *beyond* a
swing point one of two things happens:

* **Liquidity sweep (turtle soup):** price trades beyond the level and then,
  *immediately and aggressively*, reverses. The market was "not comfortable"
  above the high / below the low. The aggression is read off an opposing
  expansion-phase candle / Fair Value Gap that forms quickly after the level is
  taken (transcript 08, ~9:39 — "how do we know it's an aggressive move? By
  understanding fair value gaps, expansion phase candles").
* **Liquidity run:** price trades beyond the level and *continues* in the same
  direction. The market is "comfortable" — a same-direction expansion / FVG, or
  simply no aggressive opposing move.

We reuse :func:`mmc.core.find_fvgs` for the expansion-phase / FVG signal rather
than re-deriving expansion candles — an FVG *is* the footprint of an aggressive
move (ARCHITECTURE: never reinvent core primitives).

Polarity (ARCHITECTURE): a swing high is a bearish/premium array, so a sweep of
it reverses **bearish**; a swing low is a bullish/discount array, so a sweep of
it reverses **bullish**.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pandas as pd

from mmc.core import Direction, FairValueGap, SwingPoint, SwingType, find_fvgs


class LiquidityEvent(Enum):
    """What happened after price traded beyond a piece of liquidity."""

    SWEEP = "sweep"  # traded beyond then aggressively reversed (turtle soup)
    RUN = "run"      # traded beyond then continued (comfortable)
    NONE = "none"    # the level was never taken within the data / window


@dataclass
class LiquidityClassification:
    """Result of classifying the fate of one swing's liquidity.

    ``event``       SWEEP / RUN / NONE.
    ``swing``       the liquidity (swing point) being classified.
    ``break_index`` first bar that traded beyond the swing level (the take).
    ``signal_fvg``  the FVG whose polarity decided the call (opposing => sweep,
                    same-direction => run); ``None`` for a NONE result or a run
                    with no FVG at all.
    """

    event: LiquidityEvent
    swing: SwingPoint
    break_index: Optional[int] = None
    signal_fvg: Optional[FairValueGap] = None

    @property
    def is_sweep(self) -> bool:
        return self.event is LiquidityEvent.SWEEP

    @property
    def is_run(self) -> bool:
        return self.event is LiquidityEvent.RUN

    @property
    def reversal_direction(self) -> Optional[Direction]:
        """Direction of the move *after* a sweep (opposite of the swing array).

        A swept swing high reverses bearish; a swept swing low reverses bullish.
        ``None`` when there was no sweep.
        """
        if self.event is not LiquidityEvent.SWEEP:
            return None
        return self.swing.kind.direction


def _break_index(df: pd.DataFrame, swing: SwingPoint) -> Optional[int]:
    """First bar *after* the swing whose price trades beyond the swing level.

    For a swing high: a later bar whose ``high`` exceeds the swing price.
    For a swing low: a later bar whose ``low`` drops below the swing price.
    """
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)
    for j in range(swing.index + 1, n):
        if swing.kind is SwingType.HIGH and highs[j] > swing.price:
            return j
        if swing.kind is SwingType.LOW and lows[j] < swing.price:
            return j
    return None


def classify_liquidity(
    df: pd.DataFrame,
    swing: SwingPoint,
    window: int = 3,
    fvgs: Optional[List[FairValueGap]] = None,
) -> LiquidityClassification:
    """Classify what happened to ``swing``'s liquidity as a sweep, run or none.

    After the swing level is first taken (``break_index``), we look ``window``
    bars forward for the first FVG confirmed in that span and read its polarity:

    * an **opposing** FVG (bullish FVG after a swept low, bearish after a swept
      high) is the aggressive reversal => **SWEEP**;
    * a **same-direction** FVG (continuation) => **RUN**;
    * no FVG in the window => **RUN** (comfortable — no aggressive opposing move).

    ``window`` encodes "immediately / aggressively": only an opposing FVG that
    forms *quickly* counts as a sweep (transcript 08 — sweeps "happen extremely
    fast").
    """
    brk = _break_index(df, swing)
    if brk is None:
        return LiquidityClassification(LiquidityEvent.NONE, swing)

    if fvgs is None:
        fvgs = find_fvgs(df)

    # The reversal of a swept high is bearish; of a swept low, bullish.
    opposing = swing.kind.direction  # HIGH -> BEARISH, LOW -> BULLISH

    # First FVG whose expansion candle (c2) falls within the window after the
    # break — i.e. the aggressive move that develops right after the take.
    signal: Optional[FairValueGap] = None
    for f in fvgs:
        if brk <= f.c2_index <= brk + window:
            signal = f
            break

    if signal is not None and signal.direction is opposing:
        return LiquidityClassification(
            LiquidityEvent.SWEEP, swing, break_index=brk, signal_fvg=signal
        )

    # Same-direction FVG (continuation) or no FVG at all => comfortable run.
    return LiquidityClassification(
        LiquidityEvent.RUN, swing, break_index=brk, signal_fvg=signal
    )


def mark_swept_swings(
    df: pd.DataFrame,
    swings: List[SwingPoint],
    window: int = 3,
    fvgs: Optional[List[FairValueGap]] = None,
) -> List[SwingPoint]:
    """Set ``swept`` / ``sweep_index`` on each swing that gets swept.

    Mutates the swings in place and returns the same list for chaining. A run
    (or an un-taken level) leaves ``swept`` False.
    """
    if fvgs is None:
        fvgs = find_fvgs(df)
    for s in swings:
        result = classify_liquidity(df, s, window=window, fvgs=fvgs)
        if result.is_sweep:
            s.swept = True
            s.sweep_index = result.break_index
    return swings


def liquidity_sweeps(
    df: pd.DataFrame,
    swings: List[SwingPoint],
    window: int = 3,
    fvgs: Optional[List[FairValueGap]] = None,
) -> List[LiquidityClassification]:
    """Return the :class:`LiquidityClassification` for every swept swing."""
    if fvgs is None:
        fvgs = find_fvgs(df)
    out = []
    for s in swings:
        result = classify_liquidity(df, s, window=window, fvgs=fvgs)
        if result.is_sweep:
            out.append(result)
    return out

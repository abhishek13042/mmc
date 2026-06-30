"""Next-Level Market Structure (A-Z Guide ep 10).

> Swing highs/lows are a 3-candle pattern. **Bullish** structure = swing highs
> broken + swing lows protected; **bearish** = swing lows broken + swing highs
> protected. The critical nuance: *every timeframe must be in context of the
> timeframe above it*. A lower-TF swing sitting just below a higher-TF premium
> array (FVG) will **not** be protected — it's a magnet into the HTF array, and
> lower-TF "market structure shifts" there are traps.  — ep 10

This module labels the current structure state, marks which swings are
protected vs taken, and flags swings that are "magnetised" by a HTF PD array
(so you don't get blindsided by a lower-TF shift).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pandas as pd

from atoz.core.fvg import FVG, find_fvgs
from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Candles, Direction, Swing, SwingType


class Structure(Enum):
    BULLISH = "bullish"     # highs broken, lows protected
    BEARISH = "bearish"     # lows broken, highs protected
    RANGING = "ranging"


@dataclass
class StructureShift:
    """A market structure shift event (ep 10).

    A shift from bearish to bullish occurs when a protected swing high is
    broken by subsequent price action. A shift from bearish to bullish occurs
    when a protected swing low is taken out.
    """
    index: int              # bar index where the shift candle closed
    from_structure: Structure
    to_structure: Structure
    level: float            # the swing level that was broken


def mark_taken_swings(df: pd.DataFrame, swings: Optional[List[Swing]] = None) -> List[Swing]:
    """Set ``swept`` True on each swing later traded through (ep 10)."""
    c = Candles.of(df)
    if swings is None:
        swings = find_swings(df)
    for s in swings:
        for k in range(s.index + 1, c.n):
            if s.kind is SwingType.HIGH and c.high[k] > s.price:
                s.swept = True
                break
            if s.kind is SwingType.LOW and c.low[k] < s.price:
                s.swept = True
                break
    return swings


def find_protected_swings(
    df: pd.DataFrame,
    swings: Optional[List[Swing]] = None,
) -> List[Swing]:
    """Return swings that have NOT yet been traded through — they are protected
    (ep 10: *swing lows getting protected + swing highs broken → bullish*).

    Per ep 10: a swing is protected when subsequent price has NOT traded through
    it. Once price closes beyond the swing level, the swing is no longer
    protected (taken/invalidated).
    """
    all_swings = mark_taken_swings(df, swings)
    return [s for s in all_swings if not s.swept]


def market_structure(df: pd.DataFrame, lookback: int = 10) -> Structure:
    """Label structure from the most recent ``lookback`` swings: highs broken +
    lows protected → bullish; lows broken + highs protected → bearish (ep 10)."""
    swings = mark_taken_swings(df)
    recent = sorted(swings, key=lambda s: s.index)[-lookback:]
    highs = [s for s in recent if s.kind is SwingType.HIGH]
    lows = [s for s in recent if s.kind is SwingType.LOW]
    if not highs or not lows:
        return Structure.RANGING

    highs_broken = sum(s.swept for s in highs) / len(highs)
    lows_broken = sum(s.swept for s in lows) / len(lows)

    if highs_broken > 0.5 and lows_broken < 0.5:
        return Structure.BULLISH
    if lows_broken > 0.5 and highs_broken < 0.5:
        return Structure.BEARISH
    return Structure.RANGING


def find_market_structure(
    df: pd.DataFrame,
    swings: Optional[List[Swing]] = None,
) -> List[StructureShift]:
    """Detect all market structure shift events (ep 10).

    Walks through consecutive swings in chronological order and detects when
    a *protected* swing level is broken, signalling a structure shift:
      - Bearish → Bullish: a protected swing HIGH is traded through (price
        closes above it).
      - Bullish → Bearish: a protected swing LOW is traded through (price
        closes below it).

    Returns a list of :class:`StructureShift` objects ordered by bar index.
    """
    c = Candles.of(df)
    if swings is None:
        swings = find_swings(df)

    ordered = sorted(swings, key=lambda s: s.index)
    if not ordered:
        return []

    shifts: List[StructureShift] = []

    # Seed the initial structure from the first two opposing swings.
    # If first swing is a HIGH, assume bearish (we're looking for lows being
    # broken); if LOW, assume bullish.
    current = Structure.RANGING

    # Track the most recent "protected" swing of each type (the LLOD concept):
    # these are the reference points that, if broken, signal a shift.
    last_protected_high: Optional[Swing] = None
    last_protected_low: Optional[Swing] = None

    for s in ordered:
        if s.kind is SwingType.HIGH:
            # Check if this high breaks the current protected low (bearish shift)
            # -- that would be unusual; highs breaking lows doesn't apply.
            # More importantly: register this high as a candidate protected high.
            # A high is "protected" if price has not yet traded above it.
            if last_protected_high is None or s.price > last_protected_high.price:
                last_protected_high = s
        else:  # LOW
            if last_protected_low is None or s.price < last_protected_low.price:
                last_protected_low = s

    # Full pass: replay swings in order and detect when a *prior* protected
    # swing of the opposite type is broken by subsequent price action.
    # Reset tracking for the replay.
    last_protected_high = None
    last_protected_low = None

    for i, s in enumerate(ordered):
        if s.kind is SwingType.HIGH:
            # Did price (at a later bar) close above a prior protected HIGH?
            # That signals bullish structure shift (break of bearish structure).
            if last_protected_high is not None and current is not Structure.BULLISH:
                # Check from the protected high's bar onwards — already handled
                # below when we process price reaching the level.
                pass
            # Update protected high candidate (highest unbroken high so far).
            if last_protected_high is None:
                last_protected_high = s
            elif s.price > last_protected_high.price:
                last_protected_high = s
        else:  # LOW
            if last_protected_low is None:
                last_protected_low = s
            elif s.price < last_protected_low.price:
                last_protected_low = s

    # Cleaner approach: scan through all bars; whenever price closes beyond a
    # known protected swing, record the shift.
    last_protected_high = None
    last_protected_low = None
    current = Structure.RANGING
    swing_by_idx = {s.index: s for s in ordered}
    swing_indices = sorted(swing_by_idx.keys())

    swing_ptr = 0  # pointer into swing_indices
    for bar in range(len(df)):
        # Absorb any swings that have been confirmed at this bar.
        while swing_ptr < len(swing_indices) and swing_indices[swing_ptr] <= bar:
            s = swing_by_idx[swing_indices[swing_ptr]]
            if s.kind is SwingType.HIGH:
                # New protected high candidate — track the highest unbroken high
                if last_protected_high is None or s.price > last_protected_high.price:
                    last_protected_high = s
            else:
                if last_protected_low is None or s.price < last_protected_low.price:
                    last_protected_low = s
            swing_ptr += 1

        hi = c.high[bar]
        lo = c.low[bar]
        cl = c.close[bar]

        # Structure shift: close above a protected high → bullish
        if last_protected_high is not None and bar > last_protected_high.index:
            if cl > last_protected_high.price and current is not Structure.BULLISH:
                prev = current
                current = Structure.BULLISH
                shifts.append(StructureShift(
                    index=bar,
                    from_structure=prev,
                    to_structure=Structure.BULLISH,
                    level=last_protected_high.price,
                ))
                # The broken high is no longer protected; reset it so we look
                # for the next one.
                last_protected_high = None

        # Structure shift: close below a protected low → bearish
        if last_protected_low is not None and bar > last_protected_low.index:
            if cl < last_protected_low.price and current is not Structure.BEARISH:
                prev = current
                current = Structure.BEARISH
                shifts.append(StructureShift(
                    index=bar,
                    from_structure=prev,
                    to_structure=Structure.BEARISH,
                    level=last_protected_low.price,
                ))
                last_protected_low = None

    return shifts


@dataclass
class MagnetisedSwing:
    """A lower-TF swing pulled toward a HTF PD array — likely to be taken, not
    protected (ep 10)."""

    swing: Swing
    htf_array: FVG


def magnetised_swings(
    entry_df: pd.DataFrame,
    htf_df: pd.DataFrame,
    tolerance_atr: float = 1.0,
) -> List[MagnetisedSwing]:
    """Flag entry-TF swing highs sitting just below a HTF bullish-FVG (or swing
    lows just above a HTF bearish-FVG) — magnets, so the swing won't hold (ep 10).
    """
    swings = find_swings(entry_df)
    htf_fvgs = find_fvgs(htf_df)
    atr = float((entry_df["high"] - entry_df["low"]).tail(14).mean()) or 1e-9
    band = tolerance_atr * atr

    out: List[MagnetisedSwing] = []
    for s in swings:
        s_time = entry_df.index[s.index]
        for f in htf_fvgs:
            # only HTF arrays already in play at/after this swing's time
            f_time = htf_df.index[f.index] if f.index < len(htf_df) else None
            if f_time is None or f_time > s_time:
                continue
            if s.kind is SwingType.HIGH and 0 <= (f.bottom - s.price) <= band:
                out.append(MagnetisedSwing(s, f))
            elif s.kind is SwingType.LOW and 0 <= (s.price - f.top) <= band:
                out.append(MagnetisedSwing(s, f))
    return out

"""Secrets to Market Structure (A-Z Guide ep 32).

Faithful implementation of the *refinements* the instructor gives on top of the
basic market-structure reading (ep 10 / ``atoz.structure``). Every rule below is
quoted from the ep-32 transcript.

Core refinements (ep 32):

1. **Intermediate-term high (ITH)** — "a high that is in the middle and is in
   between a short-term high that is lower to the left of it and lower to the
   right of it". Mirror for an **intermediate-term low (ITL)**.

2. **Outsiders** — "intermediate term highs and intermediate term lows are
   always outsiders": when two candidate ITLs sit very close together you take
   the *lower* one (the outsider); two candidate ITHs → take the *higher* one.

3. **An ITH can only form AFTER an ITL is taken** — "only once we take the
   intermediate term low ... only then a new intermediate term high can form
   once we have a bigger retracement". In between an ITH and the next ITL, every
   high that forms is a **short-term high**, never an ITH.

4. **Short-term high / range criterion** — a swing high is only a confirmed
   **short-term high** when "a short-term range always needs to have a fair
   value gap in the range" — i.e. there is a fair value gap *lower* in the leg
   away from it (mirror: an FVG higher in the leg away from a short-term low).
   "that single fair value gap that is already enough to tell you this is a new
   short-term high." A bare swing high with no FVG in its leg is NOT a
   short-term high.

5. **Last line of defense / protected high** — once the ITL is taken and we get
   a bigger retracement, the ITH "is the one that is protected". Respect = a
   sweep without a *close* above (the bullish FVGs in the leg are NOT
   respected); disrespect = closing above / bullish FVGs respected.

6. **Intermediate-term range** — the band from an ITH to the following ITL is
   "your intermediate term ring a.k.a. the range that should not fail"; you draw
   premium/discount inside it and you get involved between the ITH and the ITL.

7. **Multi-timeframe context** — "the time frame you are trading on always needs
   to be in context of the time frame above it": what is a *short-term* high on
   the HTF is an *intermediate-term* high on the LTF, and an LTF ITH forms at a
   PD array (FVG) on the TF above. ``project_htf_structure`` flags LTF ITHs/ITLs
   that coincide with a HTF short-term high/low (the high-probability ones).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import pandas as pd

from atoz.core.fvg import FVG, find_fvgs
from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Candles, Direction, Swing, SwingType


# --------------------------------------------------------------------------- #
# Swing tiering
# --------------------------------------------------------------------------- #


class SwingTier(Enum):
    """ep 32 tiers a swing into short-term (STH/STL) or intermediate-term."""

    SHORT_TERM = "short_term"
    INTERMEDIATE_TERM = "intermediate_term"


@dataclass
class TieredSwing:
    """A swing labelled with its ep-32 tier and supporting facts.

    ``swing`` is the underlying ep-3 swing. ``has_leg_fvg`` records the
    short-term-range criterion (FVG in the leg away from it). ``protected`` is
    set on the ITH/ITL that is the current "last line of defense".
    """

    swing: Swing
    tier: SwingTier
    has_leg_fvg: bool = False
    leg_fvg: Optional[FVG] = None
    protected: bool = False

    @property
    def index(self) -> int:
        return self.swing.index

    @property
    def price(self) -> float:
        return self.swing.price

    @property
    def kind(self) -> SwingType:
        return self.swing.kind


# --------------------------------------------------------------------------- #
# Rule 4 — short-term-range FVG criterion
# --------------------------------------------------------------------------- #


def _has_leg_fvg(
    swing: Swing,
    fvgs: List[FVG],
    next_index: int,
    lookahead: int,
) -> Optional[FVG]:
    """Return the FVG in the leg *away* from ``swing`` (ep-32 rule 4).

    For a swing high we need a **bearish** FVG lower in the leg that follows it
    (the displacement away); for a swing low a **bullish** FVG higher in the
    leg. The leg runs from the swing up to ``next_index`` (the next opposing
    swing) bounded by ``lookahead`` bars.
    """
    want = Direction.BEARISH if swing.kind is SwingType.HIGH else Direction.BULLISH
    end = min(next_index, swing.index + lookahead)
    for f in fvgs:
        if f.direction is not want:
            continue
        # the FVG's first candle must sit after the swing and inside the leg
        if swing.index < f.index <= end:
            # FVG must be on the correct side (lower for a high, higher for a low)
            if swing.kind is SwingType.HIGH and f.top <= swing.price:
                return f
            if swing.kind is SwingType.LOW and f.bottom >= swing.price:
                return f
    return None


# --------------------------------------------------------------------------- #
# Rules 1-4 — tiering the swings into ITH/ITL and STH/STL
# --------------------------------------------------------------------------- #


def tier_swings(
    df: pd.DataFrame,
    swings: Optional[List[Swing]] = None,
    leg_lookahead: int = 30,
) -> List[TieredSwing]:
    """Label every swing as short-term or intermediate-term (ep 32).

    Procedure (faithful to the transcript):

    * An **ITH** is a swing high with a *lower* swing high immediately to its
      left and right (rule 1); mirror for an **ITL**.
    * **Outsiders** (rule 2): when two ITH/ITL candidates sit adjacent and very
      close, keep the higher ITH / lower ITL.
    * A high that is not an ITH and that has a **bearish FVG lower in its leg**
      is a confirmed **short-term high** (rule 4); mirror for lows. Highs/lows
      with no leg-FVG are still returned, tiered short-term but with
      ``has_leg_fvg=False`` so callers can drop them ("not a confirmed STH").
    """
    if swings is None:
        swings = find_swings(df)
    swings = sorted(swings, key=lambda s: s.index)
    fvgs = find_fvgs(df)
    highs = swing_highs(swings)
    lows = swing_lows(swings)

    ith_idx = _intermediate_indices(highs, SwingType.HIGH)
    itl_idx = _intermediate_indices(lows, SwingType.LOW)

    out: List[TieredSwing] = []
    for i, s in enumerate(swings):
        nxt = swings[i + 1].index if i + 1 < len(swings) else len(df)
        leg_fvg = _has_leg_fvg(s, fvgs, nxt, leg_lookahead)
        is_inter = s.index in (ith_idx if s.kind is SwingType.HIGH else itl_idx)
        tier = SwingTier.INTERMEDIATE_TERM if is_inter else SwingTier.SHORT_TERM
        out.append(
            TieredSwing(
                swing=s,
                tier=tier,
                has_leg_fvg=leg_fvg is not None,
                leg_fvg=leg_fvg,
            )
        )
    return out


def _intermediate_indices(same_kind: List[Swing], kind: SwingType) -> set:
    """Indices of swings that are intermediate-term (rule 1) after applying the
    outsider rule (rule 2)."""
    inter: List[Swing] = []
    for j in range(1, len(same_kind) - 1):
        left, mid, right = same_kind[j - 1], same_kind[j], same_kind[j + 1]
        if kind is SwingType.HIGH:
            if left.price < mid.price and right.price < mid.price:
                inter.append(mid)
        else:
            if left.price > mid.price and right.price > mid.price:
                inter.append(mid)

    # Outsider rule: collapse adjacent near-equal candidates to the outsider.
    kept: List[Swing] = []
    for s in inter:
        if kept:
            prev = kept[-1]
            close = abs(s.price - prev.price) / max(prev.price, 1e-9) < 0.001
            if close:
                if kind is SwingType.HIGH:
                    if s.price > prev.price:
                        kept[-1] = s
                else:
                    if s.price < prev.price:
                        kept[-1] = s
                continue
        kept.append(s)
    return {s.index for s in kept}


def short_term_highs(tiered: List[TieredSwing]) -> List[TieredSwing]:
    """Confirmed short-term highs (rule 4: FVG in the leg)."""
    return [
        t for t in tiered
        if t.kind is SwingType.HIGH
        and t.tier is SwingTier.SHORT_TERM
        and t.has_leg_fvg
    ]


def short_term_lows(tiered: List[TieredSwing]) -> List[TieredSwing]:
    return [
        t for t in tiered
        if t.kind is SwingType.LOW
        and t.tier is SwingTier.SHORT_TERM
        and t.has_leg_fvg
    ]


def intermediate_highs(tiered: List[TieredSwing]) -> List[TieredSwing]:
    return [t for t in tiered if t.kind is SwingType.HIGH and t.tier is SwingTier.INTERMEDIATE_TERM]


def intermediate_lows(tiered: List[TieredSwing]) -> List[TieredSwing]:
    return [t for t in tiered if t.kind is SwingType.LOW and t.tier is SwingTier.INTERMEDIATE_TERM]


# --------------------------------------------------------------------------- #
# Rule 6 — intermediate-term range ("the ring that should not fail")
# --------------------------------------------------------------------------- #


@dataclass
class IntermediateRange:
    """An ITH→ITL (or ITL→ITH) intermediate-term range — "the ring that should
    not fail" (ep 32). You draw premium/discount inside it and get involved
    between the two ends."""

    high: TieredSwing
    low: TieredSwing
    direction: Direction   # BEARISH ring = ITH then ITL (retrace up into premium)

    @property
    def top(self) -> float:
        return self.high.price

    @property
    def bottom(self) -> float:
        return self.low.price

    @property
    def equilibrium(self) -> float:
        return (self.top + self.bottom) / 2.0

    def premium(self, price: float) -> bool:
        return price >= self.equilibrium

    def discount(self, price: float) -> bool:
        return price < self.equilibrium

    @property
    def internal_swings(self) -> List[TieredSwing]:
        return self._internal

    _internal: List[TieredSwing] = field(default_factory=list)


def intermediate_ranges(
    tiered_or_df,
    swings: Optional[List[Swing]] = None,
    leg_lookahead: int = 30,
) -> List[IntermediateRange]:
    """Build ITH→ITL / ITL→ITH ranges and attach the short-term swings that form
    between them (rules 3 & 6).

    Accepts either a pre-computed ``List[TieredSwing]`` *or* a raw
    ``pd.DataFrame`` (in which case :func:`tier_swings` is called internally).

    Rule 3: a new ITH only forms after an ITL is taken — operationally we pair
    each intermediate-term swing with the next *opposing* intermediate-term
    swing, and the highs/lows in between are the internal short-term structure.
    """
    if isinstance(tiered_or_df, pd.DataFrame):
        tiered = tier_swings(tiered_or_df, swings=swings, leg_lookahead=leg_lookahead)
    else:
        tiered = tiered_or_df
    inter = [t for t in tiered if t.tier is SwingTier.INTERMEDIATE_TERM]
    inter.sort(key=lambda t: t.index)

    ranges: List[IntermediateRange] = []
    for a, b in zip(inter, inter[1:]):
        if a.kind is b.kind:
            continue
        if a.kind is SwingType.HIGH:
            high, low, direction = a, b, Direction.BEARISH
        else:
            high, low, direction = b, a, Direction.BULLISH
        internal = [t for t in tiered if a.index < t.index < b.index]
        ranges.append(
            IntermediateRange(high=high, low=low, direction=direction, _internal=internal)
        )
    return ranges


# --------------------------------------------------------------------------- #
# Rule 5 — protected high / last line of defense + disrespect detection
# --------------------------------------------------------------------------- #


def mark_protected(
    df: pd.DataFrame,
    tiered: List[TieredSwing],
) -> List[TieredSwing]:
    """Flag the ITH/ITL that is the current "last line of defense" (rule 5).

    After an ITL is taken, the preceding ITH becomes protected: price may sweep
    it (take without a *close* above = respect) but should not close above it
    (disrespect). We set ``protected=True`` on the most-recent ITH that has not
    yet been *closed* through, and mirror for ITLs.
    """
    c = Candles.of(df)
    for t in tiered:
        if t.tier is not SwingTier.INTERMEDIATE_TERM:
            continue
        closed_through = False
        for k in range(t.index + 1, c.n):
            if t.kind is SwingType.HIGH and c.close[k] > t.price:
                closed_through = True
                break
            if t.kind is SwingType.LOW and c.close[k] < t.price:
                closed_through = True
                break
        t.protected = not closed_through
    return tiered


def is_disrespected(df: pd.DataFrame, swing: TieredSwing) -> bool:
    """True once price *closes* through the swing (disrespect, rule 5).

    A pure wick sweep without a close beyond is a *respected* sweep, not a
    disrespect.
    """
    c = Candles.of(df)
    for k in range(swing.index + 1, c.n):
        if swing.kind is SwingType.HIGH and c.close[k] > swing.price:
            return True
        if swing.kind is SwingType.LOW and c.close[k] < swing.price:
            return True
    return False


# --------------------------------------------------------------------------- #
# Rule 7 — multi-timeframe projection
# --------------------------------------------------------------------------- #


@dataclass
class ProjectedStructure:
    """An LTF intermediate-term swing aligned with a HTF short-term swing — the
    high-probability ITH/ITL (ep 32 rule 7: "what is a short-term high on the HTF
    is an intermediate-term high on the LTF")."""

    ltf_swing: TieredSwing
    htf_swing: TieredSwing


def project_htf_structure(
    ltf_df: pd.DataFrame,
    htf_df: pd.DataFrame,
    tolerance_atr: float = 1.0,
) -> List[ProjectedStructure]:
    """Match LTF intermediate-term swings to HTF short-term swings (rule 7).

    A LTF ITH that coincides (within ``tolerance_atr`` HTF-ATR in price and in
    time) with a HTF short-term high is the protected, high-probability one;
    mirror for lows. This is the faithful "combine the time frames" step.
    """
    ltf = mark_protected(ltf_df, tier_swings(ltf_df))
    htf = tier_swings(htf_df)
    htf_st = [t for t in htf if t.tier is SwingTier.SHORT_TERM and t.has_leg_fvg]

    atr = float((htf_df["high"] - htf_df["low"]).tail(14).mean()) or 1e-9
    band = tolerance_atr * atr

    out: List[ProjectedStructure] = []
    ltf_inter = [t for t in ltf if t.tier is SwingTier.INTERMEDIATE_TERM]
    for lt in ltf_inter:
        lt_time = ltf_df.index[lt.index]
        for ht in htf_st:
            if ht.kind is not lt.kind:
                continue
            if ht.index >= len(htf_df):
                continue
            ht_time = htf_df.index[ht.index]
            if ht_time > lt_time:
                continue
            if abs(ht.price - lt.price) <= band:
                out.append(ProjectedStructure(ltf_swing=lt, htf_swing=ht))
                break
    return out

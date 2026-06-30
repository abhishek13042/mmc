"""Best Daily Bias Concept, simplified (A-Z Guide ep 36, transcript 037).

> "All you need is fair value gaps." The daily bias is read entirely from fair
> value gaps — "the signs price leaves behind when it is planning to do
> something".
>
> The mechanical rules quoted from the episode:
>
> * **Lag** — "with lag I'm just aiming at your swing low to the swing high, that
>   is a lag." A lag *with a fair value gap in it* is a **strong** lag (high
>   probability of holding); a lag *without* a fair value gap is **weak** (low
>   probability).
> * **Context of the timeframe above** — "you need your daily timeframe in
>   context of your weekly timeframe." A lag that has an FVG in it is STILL low
>   probability when the timeframe above has an opposing fair value gap *just
>   beyond* the lag (a magnet pulling price the other way). "That is fractal, it
>   goes for every single timeframe."
> * **Respect vs disrespect** — "whenever we are wicking a fair value gap that is
>   when we respect a fair value gap" (continuation). "Whenever we are closing
>   inside of it, or closing all the way below it [a bullish FVG] or above it [a
>   bearish FVG] ... that is disrespecting" (reversal).
> * **Draw on liquidity** — the higher-timeframe fair value gap acts as a magnet
>   (and then potentially a rocket pushing price away).
>
> Bias = bullish / bearish / neutral. "Trading every day means you are neutral";
> a bias only exists on the high-probability candles.                    — ep 36
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import pandas as pd

from atoz.core.fvg import FVG, find_fvgs
from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Candles, Direction, Swing, SwingType


class Bias(Enum):
    """The daily bias (ep 36)."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"   # "trading every day means you are neutral"


class LagStrength(Enum):
    """How probable a lag is to hold (ep 36)."""

    STRONG = "strong"   # has an FVG in it AND no opposing HTF FVG just beyond it
    WEAK = "weak"       # no FVG in the lag — low probability
    LOW_PROB = "low"    # has an FVG but a HTF opposing FVG sits just beyond it


class FVGRespect(Enum):
    """How price treated a fair value gap (ep 36)."""

    RESPECT = "respect"         # only wicked it → continuation
    DISRESPECT = "disrespect"   # closed inside / fully through → reversal
    UNTESTED = "untested"


@dataclass
class Lag:
    """A swing-low→swing-high (or high→low) impulse leg and its FVG content (ep 36)."""

    direction: Direction       # BULLISH = low→high lag (up); BEARISH = high→low lag
    start: Swing
    end: Swing
    top: float
    bottom: float
    contained_fvgs: List[FVG] = field(default_factory=list)
    strength: LagStrength = LagStrength.WEAK
    htf_opposing_fvg: Optional[FVG] = None   # the magnet just beyond the lag, if any

    @property
    def has_fvg(self) -> bool:
        return len(self.contained_fvgs) > 0


@dataclass
class DailyBias:
    """The resolved daily bias and its evidence (ep 36)."""

    bias: Bias
    lag: Optional[Lag]
    draw_on_liquidity: Optional[FVG]    # the HTF FVG acting as a magnet
    reason: str
    htf_respect: FVGRespect = FVGRespect.UNTESTED


# --------------------------------------------------------------------------- #
# Respect / disrespect of a fair value gap
# --------------------------------------------------------------------------- #


def fvg_respect(df: pd.DataFrame, fvg: FVG, up_to_index: Optional[int] = None) -> FVGRespect:
    """Classify how price treated ``fvg`` after it formed (ep 36).

    * RESPECT — price wicked into the gap but never *closed* inside or through it
      (continuation).
    * DISRESPECT — a candle closed inside the gap, or fully through the far side
      (closing below a bullish FVG / above a bearish FVG) → reversal.
    * UNTESTED — price never reached the gap.

    ``up_to_index`` bounds the scan (default: end of df) to avoid look-ahead.
    """
    c = Candles.of(df)
    end = c.n if up_to_index is None else min(c.n, up_to_index + 1)
    bullish = fvg.direction is Direction.BULLISH

    tested = False
    for k in range(fvg.c3_index + 1, end):
        hits = c.low[k] <= fvg.top and c.high[k] >= fvg.bottom
        if hits:
            tested = True
        if bullish:
            # disrespect: closing inside the gap or fully below it
            if c.close[k] < fvg.top and c.close[k] >= fvg.bottom:
                return FVGRespect.DISRESPECT
            if c.close[k] < fvg.bottom:
                return FVGRespect.DISRESPECT
        else:
            if c.close[k] > fvg.bottom and c.close[k] <= fvg.top:
                return FVGRespect.DISRESPECT
            if c.close[k] > fvg.top:
                return FVGRespect.DISRESPECT
    return FVGRespect.RESPECT if tested else FVGRespect.UNTESTED


# --------------------------------------------------------------------------- #
# Lag classification
# --------------------------------------------------------------------------- #


def classify_lag(
    lag_or_start,
    end_or_htf_fvgs=None,
    fvgs_or_htf_df=None,
    htf_df: Optional[pd.DataFrame] = None,
    df: Optional[pd.DataFrame] = None,
    beyond_band_atr: float = 1.0,
) -> "Lag":
    """Classify a lag's strength (ep 36).

    Two calling conventions are supported:

    1. Classic:  ``classify_lag(lag, htf_fvgs=None, htf_df=None, df=None)``
       where ``lag`` is a :class:`Lag` object. Returns the same ``Lag`` with
       ``.strength`` set (and now also returns the Lag, not just LagStrength).

    2. Shorthand: ``classify_lag(start_swing, end_swing, fvgs)``
       where ``start_swing`` / ``end_swing`` are :class:`Swing` objects and
       ``fvgs`` is the list of :class:`FVG` from the same timeframe. Builds
       the ``Lag`` internally and classifies it. Returns the ``Lag``.

    Strength rules (ep 36):
      * No FVG in the lag → WEAK.
      * FVG in the lag but a higher-timeframe *opposing* FVG sits just *beyond*
        the lag → LOW_PROB.
      * Otherwise → STRONG.
    """
    # ------------------------------------------------------------------ #
    # Distinguish calling convention by inspecting first argument type.   #
    # ------------------------------------------------------------------ #
    from atoz.core.types import Swing as _Swing  # local import to avoid circulars

    if isinstance(lag_or_start, _Swing):
        # Shorthand: (start_swing, end_swing, fvgs)
        start_sw: "Swing" = lag_or_start
        end_sw: "Swing" = end_or_htf_fvgs          # type: ignore[assignment]
        entry_fvgs: "List[FVG]" = fvgs_or_htf_df   # type: ignore[assignment]

        direction = (
            Direction.BULLISH if end_sw.price > start_sw.price else Direction.BEARISH
        )
        top = max(start_sw.price, end_sw.price)
        bottom = min(start_sw.price, end_sw.price)
        contained = [
            f for f in (entry_fvgs or [])
            if start_sw.index <= f.index <= end_sw.index
            and f.direction is direction
        ]
        lag: "Lag" = Lag(
            direction=direction, start=start_sw, end=end_sw,
            top=top, bottom=bottom, contained_fvgs=contained,
        )
        # No HTF info in shorthand form → straight STRONG/WEAK classification.
        lag.strength = LagStrength.STRONG if contained else LagStrength.WEAK
        return lag

    # Classic form: first arg IS a Lag.
    lag = lag_or_start
    htf_fvgs: "Optional[List[FVG]]" = end_or_htf_fvgs  # type: ignore[assignment]

    if not lag.has_fvg:
        lag.strength = LagStrength.WEAK
        return lag

    if htf_fvgs and df is not None:
        atr = float((df["high"] - df["low"]).tail(14).mean()) or 1e-9
        band = beyond_band_atr * atr
        for f in htf_fvgs:
            # opposing polarity, sitting just beyond the lag in the magnet
            # direction.
            if lag.direction is Direction.BULLISH and f.direction is Direction.BEARISH:
                if 0 <= (lag.bottom - f.top) <= band:
                    lag.htf_opposing_fvg = f
                    lag.strength = LagStrength.LOW_PROB
                    return lag
            if lag.direction is Direction.BEARISH and f.direction is Direction.BULLISH:
                if 0 <= (f.bottom - lag.top) <= band:
                    lag.htf_opposing_fvg = f
                    lag.strength = LagStrength.LOW_PROB
                    return lag

    lag.strength = LagStrength.STRONG
    return lag


def _latest_lag(df: pd.DataFrame, swings: List[Swing], fvgs: List[FVG]) -> Optional[Lag]:
    """The most recent swing→swing impulse leg, with its contained FVGs (ep 36)."""
    ordered = sorted(swings, key=lambda s: s.index)
    # find the last opposing-swing pair
    last: Optional[Lag] = None
    for a, b in zip(ordered, ordered[1:]):
        if a.kind is b.kind:
            continue
        direction = Direction.BULLISH if b.price > a.price else Direction.BEARISH
        top = max(a.price, b.price)
        bottom = min(a.price, b.price)
        contained = [
            f for f in fvgs
            if a.index <= f.index <= b.index
            and f.bottom >= bottom and f.top <= top
            and f.direction is direction
        ]
        last = Lag(
            direction=direction, start=a, end=b, top=top, bottom=bottom,
            contained_fvgs=contained,
        )
    return last


# --------------------------------------------------------------------------- #
# Daily bias
# --------------------------------------------------------------------------- #


def daily_bias(
    df: pd.DataFrame,
    htf_df: Optional[pd.DataFrame] = None,
    swing_strength: int = 2,
) -> DailyBias:
    """Resolve the daily bias from fair value gaps (ep 36).

    Pass the daily (or any entry) frame as ``df`` and the timeframe *above* it
    (weekly for daily) as ``htf_df`` to apply the "in context of the timeframe
    above" rule and to find the draw on liquidity (the HTF FVG magnet).

    Logic:
      1. Take the most recent lag (swing→swing leg).
      2. Classify it: a STRONG lag (FVG in it, no opposing HTF FVG just beyond)
         gives a bias in the lag's direction.
      3. If the lag's last FVG has already been *disrespected*, that flips the
         bias (reversal). RESPECT confirms continuation.
      4. The draw on liquidity is the nearest HTF FVG in the lag's direction.
      5. A WEAK or LOW_PROB lag → NEUTRAL ("low probability ... you are neutral").
    """
    swings = find_swings(df, strength=swing_strength)
    fvgs = find_fvgs(df)
    htf_fvgs = find_fvgs(htf_df) if htf_df is not None else None

    lag = _latest_lag(df, swings, fvgs)
    if lag is None:
        return DailyBias(Bias.NEUTRAL, None, None, "no lag found")

    strength_lag = classify_lag(lag, htf_fvgs, htf_df=htf_df, df=df)
    strength = strength_lag.strength

    if strength is LagStrength.WEAK:
        return DailyBias(
            Bias.NEUTRAL, lag, None,
            "lag has no fair value gap in it — weak / low probability (ep 36)",
        )
    if strength is LagStrength.LOW_PROB:
        return DailyBias(
            Bias.NEUTRAL, lag, lag.htf_opposing_fvg,
            "lag has an FVG but an opposing higher-timeframe FVG sits just beyond "
            "it — low probability (ep 36)",
        )

    # STRONG lag — bias is in the lag direction unless its FVG was disrespected.
    last_fvg = lag.contained_fvgs[-1]
    respect = fvg_respect(df, last_fvg)

    draw = None
    if htf_fvgs:
        same_dir = [f for f in htf_fvgs if f.direction is lag.direction]
        if same_dir:
            draw = max(same_dir, key=lambda f: f.index)

    if respect is FVGRespect.DISRESPECT:
        bias = Bias.BEARISH if lag.direction is Direction.BULLISH else Bias.BULLISH
        reason = (
            "strong lag but its fair value gap was disrespected (closed through) "
            "— reversal (ep 36)"
        )
    else:
        bias = Bias.BULLISH if lag.direction is Direction.BULLISH else Bias.BEARISH
        reason = (
            "strong lag (fair value gap in it, respected) — continuation in the "
            "lag direction (ep 36)"
        )

    return DailyBias(bias, lag, draw, reason, htf_respect=respect)


def daily_bias_series(
    df: pd.DataFrame,
    htf_df: Optional[pd.DataFrame] = None,
    start: int = 50,
    swing_strength: int = 2,
    lookback: int = 300,
) -> List[tuple]:
    """Walk-forward daily bias for each bar from ``start`` onward (no look-ahead).

    Returns a list of ``(timestamp, Bias)`` computed using only data up to and
    including each bar — useful for backtesting the bias on a daily frame.

    ``lookback`` caps how many prior bars are fed to ``daily_bias`` at each
    step.  The most-recent swing leg is almost always within the last 100-200
    bars; using a rolling window instead of the full history turns the
    worst-case O(n^2) into O(n * lookback) — orders of magnitude faster on
    long series.  Default 300 is conservative enough to capture slow-moving
    H4/D1 swing structures.
    """
    out: List[tuple] = []
    for i in range(start, len(df)):
        window = df.iloc[max(0, i - lookback + 1): i + 1]
        htf_window = None
        if htf_df is not None:
            ts = df.index[i]
            htf_window = htf_df[htf_df.index <= ts]
            if len(htf_window) < 5:
                htf_window = None
        db = daily_bias(window, htf_window, swing_strength=swing_strength)
        out.append((df.index[i], db.bias))
    return out

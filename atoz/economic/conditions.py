"""LP vs HP conditions — STOP trading in low-probability conditions (A-Z Guide ep 26).

> Everyone can justify a trade ID; very few know *when* to trade. To be a
> professional there needs to be a **boundary** before we look at the chart.
> So we go over low-probability (LP) and high-probability (HP) conditions.
> Probabilities are not binary — LP is maybe a 20% day, the chance exists but the
> odds are not in your favour.  — ep 26

> **HP = clear one-sidedness.** You can make arguments to *only one side* of the
> market. 100% bullish arguments and 0% bearish (or vice-versa). The drawn
> liquidity is "so stupidly obvious"; you reach it within ~1 minute of opening
> the chart, with no convincing. "If you need to convince yourself to do
> something, then don't do it." Demand something off price and price delivers
> exactly → that is HP.  — ep 26

> **LP = a 50/50 bias** = you have *both* bullish and bearish arguments. Even
> 90% bullish / 10% bearish is still LP (it is NOT 100/0). No clear drawn
> liquidity, no clear one-sidedness. Also LP: after a **major expansion to one
> side that has already taken the drawn liquidity** (chasing / calling a
> top/bottom). Also LP (his model): trading **ahead of CPI / NFP / FOMC**.
> The non-following-through PD arrays lead to seek-and-destroy conditions.  — ep 26

> A three-candle **consolidation → expansion → consolidation** forms a fair value
> gap; that **third candle is the dangerous, unpredictable one**.  — ep 26

What is codifiable (this module turns the rule "don't trade in LP" into a label):
    * one-sidedness from a tally of bullish vs bearish arguments (HP iff 0 on one
      side);
    * the "post-expansion + drawn-liquidity-taken" LP flag from OHLC;
    * the ahead-of-CPI/NFP/FOMC LP flag (reuses :mod:`atoz.economic.roadmap`);
    * "no clear drawn liquidity" LP flag when the caller supplies the targets.
Narrative-only (NOT codified): the discretionary "10-second / 1-minute gut feel",
"if you need to convince yourself"; and the data note that LP/HP thresholds are
per-model and must be learned from a ≥100-trade sample ("my data is not your
data").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, List, Optional, Sequence

import pandas as pd

from atoz.core.types import Candles, Direction
from atoz.economic.roadmap import NewsEvent, in_blackout_window


class Probability(Enum):
    """The two condition classes (ep 26). Probability is a spectrum, not binary;
    these are the two regimes we act on."""

    HIGH = "high"   # HP — clear one-sidedness, trade it
    LOW = "low"     # LP — 50/50 bias / chasing / pre-blackout, do NOT trade


@dataclass
class Arguments:
    """A tally of bullish vs bearish arguments for the current condition (ep 26).

    "Clear one-sidedness is when you can only make arguments on one side." So an
    argument count of (bullish>0, bearish==0) is one-sided bullish, and vice
    versa. Any non-zero on both sides is a 50/50 bias = LP, *even 90/10*.
    """

    bullish: int = 0
    bearish: int = 0

    @property
    def total(self) -> int:
        return self.bullish + self.bearish

    @property
    def one_sided(self) -> Optional[Direction]:
        """The side if exactly one side has arguments, else None (mixed = 50/50)."""
        if self.bullish > 0 and self.bearish == 0:
            return Direction.BULLISH
        if self.bearish > 0 and self.bullish == 0:
            return Direction.BEARISH
        return None

    @property
    def is_one_sided(self) -> bool:
        """HP one-sidedness: 100% on one side, 0% on the other (ep 26)."""
        return self.total > 0 and self.one_sided is not None

    def bullish_fraction(self) -> float:
        return self.bullish / self.total if self.total else 0.0


@dataclass
class ConditionReport:
    """The LP/HP verdict for the current conditions (ep 26)."""

    probability: Probability
    direction: Optional[Direction]     # the one-sided direction, if HP
    reasons: List[str] = field(default_factory=list)   # LP reasons (empty if HP)

    @property
    def is_high(self) -> bool:
        return self.probability is Probability.HIGH

    @property
    def is_low(self) -> bool:
        return self.probability is Probability.LOW

    @property
    def tradeable(self) -> bool:
        """Codifies the rule: don't trade in LP (ep 26)."""
        return self.is_high


def classify_conditions(
    arguments: Arguments,
    has_clear_drawn_liquidity: bool = True,
    after_expansion_took_liquidity: bool = False,
    ahead_of_blackout: bool = False,
) -> ConditionReport:
    """Classify current conditions as HP or LP from the ep-26 criteria.

    HP requires ALL of:
      * clear one-sidedness — arguments to only one side (``arguments.is_one_sided``);
      * a clear drawn liquidity target (``has_clear_drawn_liquidity``);
      * NOT chasing after a major expansion that already took the drawn liquidity;
      * NOT trading ahead of a CPI/NFP/FOMC blackout.
    Any failure → LP, with the failing reason(s) recorded. (ep 26)
    """
    reasons: List[str] = []

    one_sided = arguments.one_sided
    if not arguments.is_one_sided:
        if arguments.total == 0:
            reasons.append("no arguments either side — nothing clear")
        else:
            pct = round(100 * arguments.bullish_fraction())
            reasons.append(
                f"50/50 bias: {pct}% bullish / {100 - pct}% bearish arguments "
                "(both sides present = LP, even 90/10)"
            )
    if not has_clear_drawn_liquidity:
        reasons.append("no clear drawn liquidity within reach")
    if after_expansion_took_liquidity:
        reasons.append(
            "major expansion already took the drawn liquidity — chasing / "
            "calling a top or bottom"
        )
    if ahead_of_blackout:
        reasons.append("trading ahead of CPI/NFP/FOMC (consolidates into the release)")

    if reasons:
        return ConditionReport(Probability.LOW, None, reasons)
    return ConditionReport(Probability.HIGH, one_sided, [])


def after_expansion_took_liquidity(
    df: pd.DataFrame,
    index: int,
    lookback: int = 5,
    expansion_atr_mult: float = 1.5,
) -> Optional[Direction]:
    """Detect the ep-26 post-expansion LP setup ending at bar ``index``.

    "We have had a major expansion to either side and we have taken a drawn
    liquidity — that is exactly a low probability condition." We look back over
    ``lookback`` bars for a run whose net displacement exceeds
    ``expansion_atr_mult`` ATR *and* that printed a new extreme (took liquidity)
    at/just before ``index``. Returns the expansion's direction if found (the
    side you would be tempted to chase), else None. No look-ahead.
    """
    c = Candles.of(df)
    if index < lookback:
        return None
    atr = float((df["high"] - df["low"]).iloc[max(0, index - 14):index + 1].mean())
    if atr <= 0:
        return None

    start = index - lookback
    net = c.close[index] - c.close[start]
    if abs(net) < expansion_atr_mult * atr:
        return None

    window_hi = max(c.high[start:index + 1])
    window_lo = min(c.low[start:index + 1])
    prior_hi = max(c.high[:start]) if start > 0 else -float("inf")
    prior_lo = min(c.low[:start]) if start > 0 else float("inf")

    if net > 0 and window_hi >= prior_hi:
        return Direction.BULLISH   # ran up and took buy-side liquidity
    if net < 0 and window_lo <= prior_lo:
        return Direction.BEARISH   # ran down and took sell-side liquidity
    return None


def is_ahead_of_blackout(
    timestamp: pd.Timestamp,
    events: Iterable[NewsEvent],
    symbol: Optional[str] = None,
) -> bool:
    """True if ``timestamp`` is on a CPI/NFP/FOMC day *before* the release (ep 26).

    "Trading ahead of CPI/NFP/FOMC ... usually consolidates ahead of that major
    news release ... that is low probability for my trading model." Reuses the
    roadmap blackout window: inside the window AND before the release time.
    """
    ts = pd.Timestamp(timestamp)
    ev = in_blackout_window(ts, events, symbol)
    return ev is not None and ts < ev.time


def classify_bar(
    df: pd.DataFrame,
    index: int,
    arguments: Arguments,
    has_clear_drawn_liquidity: bool = True,
    events: Optional[Iterable[NewsEvent]] = None,
    symbol: Optional[str] = None,
    lookback: int = 5,
    expansion_atr_mult: float = 1.5,
) -> ConditionReport:
    """Classify the conditions at OHLC bar ``index`` (ep 26).

    Combines the caller-supplied argument tally with the two OHLC/calendar LP
    flags this module can compute: the post-expansion-chase flag and the
    ahead-of-blackout flag. ``arguments`` and ``has_clear_drawn_liquidity`` remain
    the caller's discretionary read (the transcript is explicit these are a
    per-model judgement). No look-ahead.
    """
    chased = after_expansion_took_liquidity(df, index, lookback, expansion_atr_mult) is not None
    ahead = False
    if events is not None:
        ahead = is_ahead_of_blackout(df.index[index], events, symbol)
    return classify_conditions(
        arguments,
        has_clear_drawn_liquidity=has_clear_drawn_liquidity,
        after_expansion_took_liquidity=chased,
        ahead_of_blackout=ahead,
    )


@dataclass
class ThreeCandleFVG:
    """A consolidation→expansion→consolidation 3-candle group (ep 26).

    "That consolidation creates your first candle of a potential FVG, that
    expansion creates the second candle, the third candle confirms the FVG ...
    that third candle is the dangerous one because it is unpredictable."
    ``c3_index`` is the unpredictable confirming candle.
    """

    c1_index: int
    c2_index: int      # the expansion candle
    c3_index: int      # the dangerous / unpredictable confirming candle
    direction: Direction
    confirmed: bool    # whether c3 confirmed a gap (vs left it unpredictable)


def find_three_candle_fvgs(
    df: pd.DataFrame,
    expansion_atr_mult: float = 1.0,
) -> List[ThreeCandleFVG]:
    """Detect ep-26 three-candle FVG structures (consolidation-expansion-consolidation).

    Candle 2 is an expansion (range ≥ ``expansion_atr_mult`` ATR and larger than
    its neighbours). A gap is *confirmed* when candle-1 and candle-3 do not
    overlap in the expansion's direction (a real FVG); otherwise candle 3 left
    the structure unconfirmed (the "unpredictable" outcome). Marks ``c3_index``
    as the dangerous candle. No look-ahead beyond the 3-candle group.
    """
    c = Candles.of(df)
    out: List[ThreeCandleFVG] = []
    rng = (df["high"] - df["low"]).to_numpy(dtype=float)
    for i in range(1, c.n - 1):
        atr = float((df["high"] - df["low"]).iloc[max(0, i - 14):i + 1].mean())
        if atr <= 0:
            continue
        # candle 2 = the expansion: biggest of the trio and ≥ mult*ATR
        if rng[i] < expansion_atr_mult * atr:
            continue
        if not (rng[i] >= rng[i - 1] and rng[i] >= rng[i + 1]):
            continue
        bull = c.close[i] > c.open[i]
        direction = Direction.BULLISH if bull else Direction.BEARISH
        # confirmed FVG: candle-1 / candle-3 gap in the expansion direction
        if bull:
            confirmed = c.high[i - 1] < c.low[i + 1]
        else:
            confirmed = c.low[i - 1] > c.high[i + 1]
        out.append(ThreeCandleFVG(i - 1, i, i + 1, direction, confirmed))
    return out

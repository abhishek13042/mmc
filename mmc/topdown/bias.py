"""Bias / arguments engine (transcript 12 — Top-Down Analysis).

The transcript frames bias as standing *in the middle of two sides* — a bullish
side and a bearish side — each handing you **objective arguments**. The three
argument sources are explicitly named (transcript 12, ~5:27 / ~5:50):

* **Order flow** — the most-recent order flow lag's polarity. A bullish lag is a
  bullish argument (~5:33).
* **Market structure** — the intermediate-term trend (ITH/ITL). Making higher
  ITLs = bullish; lower ITHs = bearish.
* **Candle science** — the most-recent (current) candle, read through
  :mod:`mmc.candle_science`. A bullish respect / disrespect candle is a bullish
  argument (~5:13, the "respect candle from that fair value gap").

When both sides give arguments they resolve to one of two regimes (~5:51):

* **One-sided** — all the arguments are on one side and there are none on the
  other → *extremely high probability* for that direction (~6:00).
* **Mixed** — bullish *and* a little bearish → *not* high probability; "more so
  50-50" (~6:08).

We gather one argument per source **per timeframe** (the filtering process reads
several higher timeframes), accumulate them, and the net sign gives the bias
direction. ``one_sided`` is the high-probability flag; ``confidence`` scales from
~0.5 (perfectly mixed) to ~1.0 (perfectly one-sided), matching the transcript's
"50-50 vs extremely high probability" language.

This module never re-derives FVGs / swings / lags — it orchestrates the lower
layers (``mmc.core``, ``mmc.candle_science``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from mmc.candle_science import classify_candle
from mmc.core import (
    Direction,
    StructurePointType,
    Timeframe,
    find_fvgs,
    find_order_flow_lags,
    find_swings,
    intermediate_term_points,
)


@dataclass(frozen=True)
class Argument:
    """A single objective argument for one side (transcript 12, ~5:27).

    ``source`` is one of ``"order_flow"`` / ``"market_structure"`` /
    ``"candle_science"``. ``timeframe`` is where it was read. ``detail`` is a
    short human-readable reason (handy for explaining a bias).
    """

    direction: Direction
    source: str
    timeframe: Timeframe
    detail: str = ""

    @property
    def is_bullish(self) -> bool:
        return self.direction is Direction.BULLISH


@dataclass
class Bias:
    """The accumulated bias for a symbol (transcript 12).

    ``direction`` is the net side. ``bullish_args`` / ``bearish_args`` are the
    objective arguments collected from order flow + market structure + candle
    science across the analysed timeframes. ``one_sided`` is the
    high-probability flag (all arguments on one side). ``score`` is the signed
    net (``#bullish - #bearish``); ``confidence`` is the fraction of arguments on
    the winning side (0.5 = perfectly mixed/50-50, 1.0 = perfectly one-sided).
    """

    direction: Direction
    bullish_args: List[Argument] = field(default_factory=list)
    bearish_args: List[Argument] = field(default_factory=list)
    score: int = 0
    confidence: float = 0.5
    one_sided: bool = False

    @property
    def n_bullish(self) -> int:
        return len(self.bullish_args)

    @property
    def n_bearish(self) -> int:
        return len(self.bearish_args)

    @property
    def total_args(self) -> int:
        return self.n_bullish + self.n_bearish

    @property
    def arguments(self) -> List[Argument]:
        """All arguments, bullish then bearish."""
        return [*self.bullish_args, *self.bearish_args]

    @property
    def summary(self) -> str:
        side = "bullish" if self.direction is Direction.BULLISH else "bearish"
        regime = "one-sided (high probability)" if self.one_sided else "mixed (~50/50)"
        return (
            f"{side} bias — {self.n_bullish} bullish / {self.n_bearish} bearish "
            f"argument(s), {regime}, confidence {self.confidence:.2f}"
        )


# --------------------------------------------------------------------------- #
# Per-source argument extraction (one argument per source per timeframe)
# --------------------------------------------------------------------------- #


def _order_flow_argument(
    df: pd.DataFrame, tf: Timeframe, window: int
) -> Optional[Argument]:
    """Most-recent order flow lag polarity (transcript 12, ~5:33).

    "When the most recent order flow lag is a bullish order flow lag, that is a
    bullish argument."
    """
    swings = find_swings(df)
    fvgs = find_fvgs(df)
    lags = find_order_flow_lags(swings, fvgs, window=window)
    if not lags:
        return None
    lag = max(lags, key=lambda lg: lg.index)  # most recent
    return Argument(
        direction=lag.direction,
        source="order_flow",
        timeframe=tf,
        detail=f"most-recent lag is {lag.direction.name.lower()}",
    )


def _market_structure_argument(df: pd.DataFrame, tf: Timeframe) -> Optional[Argument]:
    """Intermediate-term structure trend (transcript 12, ~5:31 — market structure).

    Compare the two most-recent intermediate-term points: a higher ITL (or a
    higher-low/higher-high progression) reads bullish, a lower ITH reads
    bearish. We use the last same-type pair to judge whether structure is making
    higher lows (bullish) or lower highs (bearish).
    """
    swings = find_swings(df)
    points = intermediate_term_points(swings)
    if len(points) < 2:
        return None

    highs = [p for p in points if p.kind is StructurePointType.ITH]
    lows = [p for p in points if p.kind is StructurePointType.ITL]

    # Prefer the freshest pair (highs or lows) to read the trend.
    candidates = []
    if len(lows) >= 2:
        candidates.append(("ITL", lows[-2], lows[-1]))
    if len(highs) >= 2:
        candidates.append(("ITH", highs[-2], highs[-1]))
    if not candidates:
        return None
    # Use whichever pair is most recent (largest latest index).
    label, prev, last = max(candidates, key=lambda c: c[2].index)

    if last.price > prev.price:
        direction = Direction.BULLISH
        detail = f"higher {label} (rising structure)"
    elif last.price < prev.price:
        direction = Direction.BEARISH
        detail = f"lower {label} (falling structure)"
    else:
        return None
    return Argument(
        direction=direction,
        source="market_structure",
        timeframe=tf,
        detail=detail,
    )


def _candle_science_argument(df: pd.DataFrame, tf: Timeframe) -> Optional[Argument]:
    """Most-recent candle read via candle science (transcript 12, ~5:13 / ~2:46).

    "I only care what the next monthly candle wants to do — candle science." The
    current (last) candle's implied continuation direction is the argument.
    """
    if len(df) == 0:
        return None
    row = df.iloc[-1]
    science = classify_candle(
        float(row["open"]),
        float(row["high"]),
        float(row["low"]),
        float(row["close"]),
    )
    return Argument(
        direction=science.direction,
        source="candle_science",
        timeframe=tf,
        detail=science.label,
    )


# --------------------------------------------------------------------------- #
# Accumulation
# --------------------------------------------------------------------------- #


def compute_bias(
    data_by_tf: Dict[Timeframe, pd.DataFrame],
    timeframes: Optional[List[Timeframe]] = None,
    window: int = 3,
    one_sided_min_args: int = 2,
) -> Bias:
    """Accumulate objective arguments into a :class:`Bias` (transcript 12).

    Parameters
    ----------
    data_by_tf
        ``{Timeframe: DataFrame}`` as returned by
        :func:`mmc.data.load_all_timeframes`.
    timeframes
        Which timeframes to read (ordered high → low). Defaults to every
        timeframe present in ``data_by_tf``, highest first.
    window
        Order-flow lag window passed to the core layer.
    one_sided_min_args
        Minimum number of total arguments before a one-sided collection counts
        as *high probability*. With a single lone argument we don't claim the
        "extremely high probability" regime.

    For each timeframe we gather (at most) one argument from each of the three
    sources — order flow, market structure, candle science — and accumulate them.
    The net sign sets the bias direction; ``one_sided`` flags the
    all-on-one-side, high-probability case.
    """
    if timeframes is None:
        timeframes = sorted(data_by_tf.keys(), reverse=True)  # high → low

    bullish: List[Argument] = []
    bearish: List[Argument] = []

    for tf in timeframes:
        df = data_by_tf.get(tf)
        if df is None or len(df) == 0:
            continue
        for arg in (
            _order_flow_argument(df, tf, window),
            _market_structure_argument(df, tf),
            _candle_science_argument(df, tf),
        ):
            if arg is None:
                continue
            (bullish if arg.is_bullish else bearish).append(arg)

    n_bull, n_bear = len(bullish), len(bearish)
    score = n_bull - n_bear
    total = n_bull + n_bear

    if score >= 0:
        direction = Direction.BULLISH
        winning = n_bull
    else:
        direction = Direction.BEARISH
        winning = n_bear

    # One-sided = arguments entirely on the winning side, with enough of them to
    # call it the "extremely high probability" regime (transcript ~6:00).
    losing = total - winning
    one_sided = total >= one_sided_min_args and losing == 0 and winning > 0

    confidence = (winning / total) if total else 0.5

    return Bias(
        direction=direction,
        bullish_args=bullish,
        bearish_args=bearish,
        score=score,
        confidence=confidence,
        one_sided=one_sided,
    )

"""Top-down analysis (transcript 12 — A Top-Down Analysis that suits YOU).

The purpose of a top-down is **not** entry; it is to find, in order
(transcript 12, ~0:41):

1. the **direction** in price,
2. the **narrative**,
3. a high-probability **context area** where we then look for entries.

This module runs that chain. The direction/narrative come from the bias engine
(:mod:`mmc.topdown.bias`) — the accumulated objective arguments. The context
area comes from the context layer (:func:`mmc.context.find_context_areas`) on the
style's context timeframe. The entry itself is deliberately *out of scope*
(~0:32).

A :class:`StyleConfig` decides which timeframes are read and how far down we
drill: the filtering-process trader only descends to the 4H, and only if it
already has daily/weekly/monthly context (~6:38); the flow trader drills lower,
guided by 15m/1H FVGs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

import pandas as pd

from mmc.context import ContextArea, find_context_areas
from mmc.core import Direction, Timeframe

from .bias import Bias, compute_bias
from .style import (
    HTF_CONTEXT_TIMEFRAMES,
    StyleConfig,
    TraderStyle,
    style_config,
)


@dataclass
class TopDownResult:
    """The output of a top-down (transcript 12): direction → narrative → context.

    Attributes
    ----------
    symbol
        The instrument analysed (may be ``""`` for raw synthetic data).
    style
        The trader style used.
    bias
        The accumulated bias (direction + objective arguments + one_sided flag).
    context_timeframe
        Which timeframe the context areas were located on.
    context_areas
        The high-probability context areas (aligned to the bias direction) where
        we now look for entries. Empty if none were found.
    narrative
        A short human summary of the direction / narrative.
    drilled_to_lower
        Whether the style was permitted to drill down to its lower context
        timeframe (filtering process: only with prior HTF context).
    """

    symbol: str
    style: TraderStyle
    bias: Bias
    context_timeframe: Timeframe
    context_areas: List[ContextArea] = field(default_factory=list)
    narrative: str = ""
    drilled_to_lower: bool = False

    @property
    def direction(self) -> Direction:
        return self.bias.direction

    @property
    def one_sided(self) -> bool:
        return self.bias.one_sided

    @property
    def probability(self) -> float:
        """Convenience probability score in ``[0, 1]`` — the bias confidence."""
        return self.bias.confidence

    @property
    def best_context(self) -> Optional[ContextArea]:
        return self.context_areas[0] if self.context_areas else None


def _has_htf_context(
    data_by_tf: Dict[Timeframe, pd.DataFrame],
    direction: Direction,
    window: int,
) -> bool:
    """Does the symbol already have daily/weekly/monthly context aligned to the
    bias direction? (transcript 12, ~6:47 — the gate before drilling to 4H.)

    We have no weekly/monthly data, so D1 stands in for "higher-timeframe
    context": a context area on the daily that points the bias direction.
    """
    for tf in HTF_CONTEXT_TIMEFRAMES:
        df = data_by_tf.get(tf)
        if df is None or len(df) == 0:
            continue
        for area in find_context_areas(df, window=window):
            if area.direction is direction:
                return True
    return False


def _narrative_summary(symbol: str, bias: Bias, tf: Timeframe) -> str:
    """A short direction/narrative sentence for the result."""
    side = "bullish" if bias.direction is Direction.BULLISH else "bearish"
    sym = symbol or "instrument"
    return (
        f"{sym}: {side} top-down — {bias.summary}. "
        f"Look for entries in {side} context on {tf.name}."
    )


def top_down(
    symbol_or_data: Union[str, Dict[Timeframe, pd.DataFrame]],
    style: TraderStyle = TraderStyle.FILTERING_PROCESS,
    timeframes: Optional[List[Timeframe]] = None,
    data_dir=None,
    bars: Optional[int] = None,
    window: int = 3,
) -> TopDownResult:
    """Run the full top-down chain for one instrument and return a result.

    ``symbol_or_data`` is either a symbol string (data is loaded via
    :func:`mmc.data.load_all_timeframes`) or a ``{Timeframe: DataFrame}`` dict
    (e.g. small synthetic frames for tests).

    Chain (transcript 12, ~0:41): compute the **bias** (direction + narrative
    arguments) on the style's bias timeframes, then locate high-probability
    **context areas** on the style's context timeframe — drilling to the lower
    timeframe only when the style permits (filtering process requires prior HTF
    context, ~6:38).
    """
    cfg: StyleConfig = style_config(style)

    if isinstance(symbol_or_data, str):
        # Local import keeps the data layer optional for synthetic-only use.
        from mmc.data import load_all_timeframes

        symbol = symbol_or_data
        data_by_tf = load_all_timeframes(symbol, data_dir=data_dir)
    else:
        symbol = ""
        data_by_tf = symbol_or_data

    if bars is not None:
        data_by_tf = {
            tf: (df.iloc[-bars:] if len(df) > bars else df)
            for tf, df in data_by_tf.items()
        }

    available = list(data_by_tf.keys())

    # 1) Direction + narrative — the bias from objective arguments.
    bias_tfs = timeframes if timeframes is not None else cfg.bias_tfs_present(available)
    bias = compute_bias(data_by_tf, timeframes=bias_tfs or None, window=window)

    # 2) Decide whether we may drill to the (lower) context timeframe.
    context_tf = cfg.context_timeframe
    drilled = True
    if cfg.requires_htf_context_before_drill and context_tf not in HTF_CONTEXT_TIMEFRAMES:
        if _has_htf_context(data_by_tf, bias.direction, window):
            drilled = True
        else:
            drilled = False
            # Fall back to the highest available HTF for context.
            for tf in HTF_CONTEXT_TIMEFRAMES:
                if tf in data_by_tf:
                    context_tf = tf
                    break

    # 3) Context areas on the chosen timeframe, aligned to the bias direction.
    context_areas: List[ContextArea] = []
    ctx_df = data_by_tf.get(context_tf)
    if ctx_df is not None and len(ctx_df):
        context_areas = [
            a
            for a in find_context_areas(ctx_df, window=window)
            if a.direction is bias.direction
        ]

    return TopDownResult(
        symbol=symbol,
        style=style,
        bias=bias,
        context_timeframe=context_tf,
        context_areas=context_areas,
        narrative=_narrative_summary(symbol, bias, context_tf),
        drilled_to_lower=drilled,
    )

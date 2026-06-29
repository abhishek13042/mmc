"""Trader styles & per-style configuration (transcript 12 — Top-Down Analysis).

The transcript's core message is that a top-down is **personal**: which concept
you read on which timeframe, and how far down you drill, depends on the trader
you want to be. It then splits traders into two concrete paths:

* **Filtering-process trader** (transcript 12, ~3:38) — focuses on the *higher*
  timeframe, scans *many* Forex pairs, and uses *arguments* (order flow + market
  structure + candle science) to pick the single highest-probability pair. Stops
  drilling at the 4H, and only goes to 4H if already in daily/weekly/monthly
  context (~6:38). Low trade frequency (~1 great trade/week).

* **Flow trader** (transcript 12, ~9:26) — focuses on the *lower* timeframe, one
  *single* (ideally most-volatile) instrument, reacting "ping-pong" and guided by
  15m & 1H FVGs toward higher-TF PD arrays. Higher trade frequency.

This module is pure configuration — no detection logic. The bias / top-down
engines read a :class:`StyleConfig` to decide which timeframes to analyse and how
far down to drill for context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple

from mmc.core.types import Timeframe


class TraderStyle(Enum):
    """The two top-down paths of transcript 12."""

    FILTERING_PROCESS = "filtering_process"
    FLOW = "flow"


@dataclass(frozen=True)
class StyleConfig:
    """How a given :class:`TraderStyle` runs its top-down (transcript 12).

    Attributes
    ----------
    style
        Which path this config describes.
    bias_timeframes
        The (higher) timeframes the *arguments* engine reads to form a bias,
        ordered high → low. The filtering process leans on monthly/weekly/daily;
        the flow trader still reads the higher TF but takes fewer peaks at it.
    context_timeframe
        The timeframe on which the high-probability *context area* is located.
    drill_floor
        The lowest timeframe the style is allowed to drill *down* to during the
        top-down. The filtering process stops at the 4H (``H4``); the flow trader
        goes much lower (``M5`` here — the lowest timeframe in our data; the
        transcript says down to the 1m).
    requires_htf_context_before_drill
        Filtering-process rule (~6:38): only descend to the 4H/lower if you
        *already* have daily/weekly/monthly context. The flow trader has no such
        restriction (it is guided lower by 15m/1H FVGs).
    multi_instrument
        Filtering process scans many pairs; the flow trader commits to one.
    guide_timeframes
        Flow-trader specific: the FVG "guide" timeframes (15m & 1H) that point
        toward the next higher-TF PD array (~13:31). Empty for filtering process.
    """

    style: TraderStyle
    bias_timeframes: Tuple[Timeframe, ...]
    context_timeframe: Timeframe
    drill_floor: Timeframe
    requires_htf_context_before_drill: bool
    multi_instrument: bool
    guide_timeframes: Tuple[Timeframe, ...] = field(default_factory=tuple)

    def bias_tfs_present(self, available: List[Timeframe]) -> List[Timeframe]:
        """The configured bias timeframes that actually exist in ``available``,
        ordered high → low (skips any timeframe we have no data for)."""
        present = set(available)
        return [tf for tf in self.bias_timeframes if tf in present]


# Higher-timeframe-first ordering used throughout the top-down.
_HTF_FIRST: Tuple[Timeframe, ...] = (
    Timeframe.D1,
    Timeframe.H4,
    Timeframe.H1,
    Timeframe.M15,
    Timeframe.M5,
)

# A timeframe is "higher-timeframe context" (transcript 12, ~6:47) if it is D1 or
# above. In our dataset D1 is the highest available, so daily counts.
HTF_CONTEXT_TIMEFRAMES: Tuple[Timeframe, ...] = (Timeframe.D1,)


FILTERING_PROCESS_CONFIG = StyleConfig(
    style=TraderStyle.FILTERING_PROCESS,
    # Higher-timeframe arguments first: daily, then 4H (we have no weekly/monthly
    # in the dataset, so D1 stands in for the htf market-structure read).
    bias_timeframes=(Timeframe.D1, Timeframe.H4),
    context_timeframe=Timeframe.H4,
    drill_floor=Timeframe.H4,  # stops at the 4H (~9:43)
    requires_htf_context_before_drill=True,
    multi_instrument=True,
    guide_timeframes=(),
)

FLOW_CONFIG = StyleConfig(
    style=TraderStyle.FLOW,
    # Still reads the higher TF, but the lower timeframes carry the bias / flow.
    bias_timeframes=(Timeframe.H1, Timeframe.M15),
    context_timeframe=Timeframe.M15,
    drill_floor=Timeframe.M5,  # lowest TF in our data (transcript: down to 1m)
    requires_htf_context_before_drill=False,
    multi_instrument=False,
    guide_timeframes=(Timeframe.H1, Timeframe.M15),  # the FVG guides (~13:31)
)


_CONFIGS = {
    TraderStyle.FILTERING_PROCESS: FILTERING_PROCESS_CONFIG,
    TraderStyle.FLOW: FLOW_CONFIG,
}


def style_config(style: TraderStyle) -> StyleConfig:
    """Return the canonical :class:`StyleConfig` for ``style``."""
    return _CONFIGS[style]

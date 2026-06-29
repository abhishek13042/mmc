"""MMC context layer (transcript 10 — Usual & Unusual Context).

**Context = the objective area where we look for an entry**: from a *boundary*
(a narrative PD array we enter from — FVG / FVA / swing point) to the *target*
(the first opposing PD array we trade towards). Both are mechanical/objective.

We always trade **usual context**. **Unusual context** is the bigger picture
where an FVA stops offering fair value (failed rejection -> opposing FVG) and
starts seeking liquidity (target = the FVA's far side); the FVG we then trade is
itself a usual context area.

This layer sits on ``mmc.core`` + ``mmc.narrative`` + ``mmc.sweeps`` and never
re-derives FVGs / swings / lags / sweeps.

Public API
----------
``ContextArea``
    The context-area dataclass (boundary, target, direction, kind, defense).
``find_context_areas(df, ...)``
    All usual context areas (FLOD / ODD / LOD).
``find_unusual_context(df, ...)``
    Unusual-context areas (FVA seeking liquidity -> usual-context opposing FVG).
``first_opposing_pd_array(direction, from_index, df, swings, fvgs)``
    The mechanical context-target rule (nearest opposing swing, else FVG, else
    previous candle high/low).
"""

from .area import ContextArea
from .targets import first_opposing_pd_array
from .unusual import find_unusual_context
from .usual import find_context_areas

__all__ = [
    "ContextArea",
    "find_context_areas",
    "find_unusual_context",
    "first_opposing_pd_array",
]

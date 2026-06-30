"""atoz.playstyles — swing-around-a-job and advanced scalping (A-Z Guide ep 35 & 37).

ep 35 (swing_fulltime.py) — "Trading with a Fulltime Job? No Problem! (Lost Art)":
    Weekend scanning → HTF context band → limit-order set-and-forget, no intraday
    monitoring needed. Monthly/Weekly/Daily context → 4h/1h/1h entry timeframe.
        Context, OrderType, SwingPlayStyle, ContextBand, LimitOrderSetup,
        find_context_bands, precompute_limit_setups, find_reentry_setups, break_even_when

ep 37 (advanced_scalping.py) — "Advanced Scalping Guide":
    Daily-bias gate + 1h/15m boundary (PD array tapped at killzone/news) + LTF
    (1m/5m) ST trigger. What differentiates a strong 1m FVG from a random one.
        ScalpEntryTF, BoundaryTF, Boundary, ScalpEntry,
        daily_bias, find_boundaries, find_scalp_entries
"""

from .swing_fulltime import (
    Context,
    OrderType,
    SwingPlayStyle,
    ContextBand,
    LimitOrderSetup,
    find_context_bands,
    precompute_limit_setups,
    find_reentry_setups,
    break_even_when,
)
from .advanced_scalping import (
    ScalpEntryTF,
    BoundaryTF,
    Boundary,
    ScalpEntry,
    daily_bias,
    find_boundaries,
    find_scalp_entries,
)

__all__ = [
    # ep 35 — swing with fulltime job
    "Context", "OrderType", "SwingPlayStyle",
    "ContextBand", "find_context_bands",
    "LimitOrderSetup", "precompute_limit_setups", "find_reentry_setups", "break_even_when",
    # ep 37 — advanced scalping
    "ScalpEntryTF", "BoundaryTF", "Boundary", "ScalpEntry",
    "daily_bias", "find_boundaries", "find_scalp_entries",
]

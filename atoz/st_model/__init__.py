"""atoz.st_model — the ST (Sharp Turn) model & the "most accurate" entry pattern.

Two episodes of the A-Z Guide, implemented faithfully:

    ep 22 (entry_pattern.py) — "Most Accurate Entry Pattern (Trading Plan)":
        How far does price retrace before it continues? Answer: the FIRST
        overlapping PD array (a fair value gap overlapping a discount block),
        near equilibrium. Dealing-range Fibonacci / OTE scaffold + stop placement.
            find_entry_patterns, STEntry, DealingRange, EntryStyle, StopStyle,
            FIB_LEVELS, OTE, EQUILIBRIUM

    ep 23 (st.py) — "Market Structure Shift is BS (ST Model)":
        You don't need a market structure shift if you use fair value gaps. The
        ST ("sharp turn") model: displacement -> retracement -> displacement
        (highest probability), and the advanced single-new-FVG entry that fires
        *before* any MSS.
            find_st_setups, STSetup, STForm

Quick start::

    from mmc.data import load
    from mmc.core.types import Timeframe
    from atoz.blocks import find_all_blocks
    import atoz.st_model as m

    df = load("EURUSD", Timeframe.H1).tail(2000)
    st = m.find_st_setups(df)                          # ep 23
    ep22 = m.find_entry_patterns(df, blocks=find_all_blocks(df))  # ep 22
"""

from .entry_pattern import (
    EQUILIBRIUM,
    FIB_LEVELS,
    OTE,
    DealingRange,
    EntryStyle,
    STEntry,
    StopStyle,
    build_dealing_range,
    find_entry_patterns,
)
from .st import STForm, STSetup, find_st_setups

__all__ = [
    # ep 22 — most accurate entry pattern
    "find_entry_patterns", "STEntry", "DealingRange", "build_dealing_range",
    "EntryStyle", "StopStyle", "FIB_LEVELS", "OTE", "EQUILIBRIUM",
    # ep 23 — ST (sharp turn) model
    "find_st_setups", "STSetup", "STForm",
]

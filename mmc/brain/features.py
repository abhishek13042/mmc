"""Feature extraction for the MMC decision brain.

Each feature maps to one or more lecture concepts so the neural network learns
*named* trading knowledge, not raw price patterns:

    Timing     → ep 16 (killzones: London 09-12, NY 14-17 broker EET)
    HTF bias   → ep 9/10 (FLOD / ODD / unusual context on D1/H4)
    Sweep/Run  → liquidity masterclass (two-sting, red zone, confirmation)
    PD arrays  → ep 1-7 (OB, FVG, BPR, FVA quality)
    Order flow → ep 8-9 (FLOD, ODD, LOD, unusual)
    Entry      → ep 11-12 (sharp turn, order flow, fast turn)
    RR         → ANALYSIS.md (min_rr = 2.0 sweet spot)
    SMT        → ep 13 (divergence between correlated pairs)
    Structure  → ep 10 (running highs/lows = bullish/bearish trend)

Broker timezone: EET (UTC+2 winter / UTC+3 summer).
Because EET and NY both shift for DST, NY-referenced times are *constant*
in broker time:
    London KZ  → 09:00–12:00 broker
    NY AM KZ   → 14:00–17:00 broker
    Asia       → 21:00–07:00 broker
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from mmc.core import (
    Direction,
    FairValueArea,
    SwingType,
    find_fvgs,
    find_order_flow_lags,
    find_swings,
    intermediate_term_points,
    mark_mitigation,
    swing_highs,
    swing_lows,
)
from mmc.sweeps.liquidity import LiquidityEvent, classify_liquidity

FEATURE_NAMES: List[str] = [
    # Timing — ep 16
    "in_london_kz",
    "in_ny_kz",
    "in_asia",
    "session_hour_sin",
    "session_hour_cos",
    # HTF context — ep 9/10
    "htf_bias",
    "htf_flod",
    "htf_odd",
    "htf_unusual",
    # Sweep/run — liquidity masterclass
    "sweep_detected",
    "run_detected",
    "two_sting",
    "red_zone",
    # PD arrays — ep 1-7
    "fvg_present",
    "fvg_quality",
    "bpr_present",
    "ob_present",
    "fva_fresh",
    "fva_mitigated",
    # Order-flow context — ep 8-10
    "flod_present",
    "odd_present",
    "unusual_context",
    "lod_only",
    # Entry — ep 11-12
    "sharp_turn",
    "order_flow_entry",
    "entry_fast",
    # Risk/reward
    "r_to_tp",
    # SMT — ep 13
    "smt_bullish",
    "smt_bearish",
    # Market structure — ep 10
    "running_highs",
    "running_lows",
]

N_FEATURES = len(FEATURE_NAMES)


# ---------------------------------------------------------------------------
# Timing helpers (broker EET — stable across DST because both clocks shift)
# ---------------------------------------------------------------------------

def _session_flags(hour: int) -> Dict[str, float]:
    """Return killzone membership flags for a broker-time hour."""
    return {
        "in_london_kz": float(9 <= hour < 12),
        "in_ny_kz":     float(14 <= hour < 17),
        "in_asia":      float(hour >= 21 or hour < 7),
        "session_hour_sin": math.sin(2 * math.pi * hour / 24),
        "session_hour_cos": math.cos(2 * math.pi * hour / 24),
    }


# ---------------------------------------------------------------------------
# HTF bias helper
# ---------------------------------------------------------------------------

def _htf_bias(htf_df: Optional[pd.DataFrame], bar_time: pd.Timestamp) -> Dict[str, float]:
    """Derive HTF bias at ``bar_time`` from the context-timeframe DataFrame.

    Running highs → bullish (+1), running lows → bearish (-1), else neutral.
    Looks back over the last 20 HTF bars to find the dominant structure.
    """
    out = {"htf_bias": 0.0, "htf_flod": 0.0, "htf_odd": 0.0, "htf_unusual": 0.0}
    if htf_df is None:
        return out

    slice_df = htf_df.loc[htf_df.index <= bar_time].tail(30)
    if len(slice_df) < 6:
        return out

    swings = find_swings(slice_df.reset_index(drop=True))
    highs = swing_highs(swings)
    lows  = swing_lows(swings)

    running_highs = (
        len(highs) >= 2
        and highs[-1].price > highs[-2].price
    )
    running_lows = (
        len(lows) >= 2
        and lows[-1].price < lows[-2].price
    )

    if running_highs and not running_lows:
        out["htf_bias"] = 1.0
    elif running_lows and not running_highs:
        out["htf_bias"] = -1.0

    # HTF defense: decompose the most recent lag so the FVA is attached and we
    # can tell FLOD (FVG hit first) from ODD (FVA hit first). Without
    # decompose_lag + fvas, lag.fva is always None and htf_odd never fires.
    rs = slice_df.reset_index(drop=True)
    fvgs = find_fvgs(rs)
    if fvgs:
        from mmc.core import fair_value_areas, intermediate_term_points
        from mmc.narrative import decompose_lag

        fvas = fair_value_areas(intermediate_term_points(swings))
        lags = find_order_flow_lags(swings, fvgs)
        if lags:
            lg = lags[-1]
            decompose_lag(lg, df=rs, fvas=fvas)
            if lg.flod is not None:
                # FLOD = FVG -> high-prob FLOD context; FLOD = FVA -> ODD context
                if isinstance(lg.flod, FairValueArea):
                    out["htf_odd"] = 1.0
                else:
                    out["htf_flod"] = 1.0

    # HTF unusual context (FVA seeking liquidity on the higher timeframe)
    try:
        from mmc.context import find_unusual_context
        if find_unusual_context(rs):
            out["htf_unusual"] = 1.0
    except Exception:
        pass

    return out


# ---------------------------------------------------------------------------
# Sweep / run / red-zone / two-sting (liquidity masterclass)
# ---------------------------------------------------------------------------

def _sweep_run_features(
    df: pd.DataFrame,
    bar_idx: int,
    look_back: int = 20,
) -> Dict[str, float]:
    """Classify the most recent liquidity event visible at ``bar_idx``.

    Returns:
        sweep_detected  — 1.0 if the most recent swing was swept
        run_detected    — 1.0 if the most recent swing was run
        two_sting       — 1.0 if a run was confirmed by a second sting below/above
        red_zone        — 1.0 if price is stuck between a swept swing and its OB+FVG
    """
    out = {"sweep_detected": 0.0, "run_detected": 0.0,
           "two_sting": 0.0, "red_zone": 0.0}

    start = max(0, bar_idx - look_back)
    sub = df.iloc[start:bar_idx + 1].reset_index(drop=True)
    if len(sub) < 5:
        return out

    swings = find_swings(sub)
    if not swings:
        return out

    fvgs = find_fvgs(sub)

    # Classify the most recent swing
    last = swings[-1]
    result = classify_liquidity(sub, last, window=3, fvgs=fvgs)

    if result.event is LiquidityEvent.SWEEP:
        out["sweep_detected"] = 1.0
        # Red zone: price is above/below the swept swing but hasn't broken
        # through the opposing OB+FVG yet — the 50/50 zone (liquidity masterclass)
        if result.break_index is not None:
            brk = result.break_index
            # If there's an opposing FVG after the break, we're in the red zone
            # until the FVG's far edge is either respected or broken
            opposing_dir = last.kind.direction
            opp_fvgs = [
                f for f in fvgs
                if f.direction is opposing_dir and f.c1_index >= brk
            ]
            if opp_fvgs:
                f0 = opp_fvgs[0]
                cur_close = float(df["close"].iloc[bar_idx])
                if opposing_dir is Direction.BEARISH:
                    # Swept high: opposing FVG is bearish, red zone = price < FVG top
                    out["red_zone"] = float(cur_close < f0.top)
                else:
                    # Swept low: opposing FVG is bullish, red zone = price > FVG bottom
                    out["red_zone"] = float(cur_close > f0.bottom)

    elif result.event is LiquidityEvent.RUN:
        out["run_detected"] = 1.0
        # Two-sting: first break → retrace → second break (liquidity masterclass)
        out["two_sting"] = float(_two_sting_confirmed(sub, last, fvgs))

    return out


def _two_sting_confirmed(
    df: pd.DataFrame,
    swing,
    fvgs,
    retrace_pct: float = 0.3,
) -> bool:
    """True if a second sting (retrace then re-break) is visible after the
    first sting below/above ``swing``.

    Pattern: first break → partial retrace → second break further beyond.
    The retrace must pull back at least ``retrace_pct`` of the initial sting
    range to count as a meaningful two-sting (not just noise).
    """
    highs = df["high"].to_numpy()
    lows  = df["low"].to_numpy()
    n = len(df)
    swing_price = swing.price
    is_high = swing.kind is SwingType.HIGH

    # Find first break
    first_break = None
    for j in range(swing.index + 1, n):
        if is_high and highs[j] > swing_price:
            first_break = j
            break
        if not is_high and lows[j] < swing_price:
            first_break = j
            break

    if first_break is None or first_break + 2 >= n:
        return False

    # Find retrace after first break
    sting_price = highs[first_break] if is_high else lows[first_break]
    sting_range = abs(sting_price - swing_price)
    if sting_range == 0:
        return False

    retrace_found = False
    retrace_end = first_break
    for j in range(first_break + 1, n):
        if is_high:
            retrace_depth = (sting_price - lows[j]) / sting_range
        else:
            retrace_depth = (highs[j] - sting_price) / sting_range
        if retrace_depth >= retrace_pct:
            retrace_found = True
            retrace_end = j
            break

    if not retrace_found:
        return False

    # Find second sting beyond the first
    for j in range(retrace_end + 1, n):
        if is_high and highs[j] > sting_price:
            return True
        if not is_high and lows[j] < sting_price:
            return True

    return False


# ---------------------------------------------------------------------------
# PD array features (ep 1–7)
# ---------------------------------------------------------------------------

def _pd_array_features(
    df: pd.DataFrame,
    bar_idx: int,
    direction: Optional[Direction] = None,
    look_back: int = 20,
) -> Dict[str, float]:
    """Score the quality and type of PD arrays at ``bar_idx``."""
    out = {
        "fvg_present": 0.0, "fvg_quality": 0.0, "bpr_present": 0.0,
        "ob_present": 0.0, "fva_fresh": 0.0, "fva_mitigated": 0.0,
    }

    start = max(0, bar_idx - look_back)
    sub = df.iloc[start:bar_idx + 1].reset_index(drop=True)
    if len(sub) < 3:
        return out

    fvgs = find_fvgs(sub)
    mark_mitigation(sub, fvgs)

    # Filter by direction if given
    relevant = [f for f in fvgs if direction is None or f.direction is direction]
    if not relevant:
        return out

    # Most recent relevant FVG
    f = relevant[-1]
    out["fvg_present"] = 1.0

    # Quality scoring (ep 7: nested, overlapping, volume imbalance, BPR)
    quality = 0.0
    if getattr(f, "quality", None) is not None:
        quality = float(f.quality)
    else:
        # Fallback: score by size relative to recent ATR
        atr = _atr(sub, 14)
        fvg_size = f.top - f.bottom
        quality = min(3.0, fvg_size / atr * 1.5) if atr > 0 else 0.0
    out["fvg_quality"] = quality / 3.0  # normalise 0-1

    # BPR: Balanced Price Range = bullish FVG overlapping bearish FVG (ep 7)
    bull_fvgs = [g for g in fvgs if g.direction is Direction.BULLISH]
    bear_fvgs = [g for g in fvgs if g.direction is Direction.BEARISH]
    bpr = any(
        bg.bottom <= ug.top and bg.top >= ug.bottom
        for bg in bear_fvgs for ug in bull_fvgs
    )
    out["bpr_present"] = float(bpr)

    # Order block: the swing + retracement before the FVG (ep 1-2)
    swings = find_swings(sub)
    out["ob_present"] = float(bool(swings))

    # FVA freshness
    out["fva_fresh"]    = float(not getattr(f, "mitigated", False))
    out["fva_mitigated"] = float(getattr(f, "mitigated", False))

    return out


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    if len(df) < 2:
        return 1e-8
    trs = (df["high"] - df["low"]).abs().tail(period)
    return float(trs.mean()) if len(trs) > 0 else 1e-8


# ---------------------------------------------------------------------------
# Order-flow context features (ep 8–10)
# ---------------------------------------------------------------------------

def _context_features(
    df: pd.DataFrame,
    bar_idx: int,
    look_back: int = 30,
) -> Dict[str, float]:
    """Detect FLOD / ODD / unusual / LOD context at ``bar_idx``."""
    out = {
        "flod_present": 0.0, "odd_present": 0.0,
        "unusual_context": 0.0, "lod_only": 0.0,
    }

    start = max(0, bar_idx - look_back)
    sub = df.iloc[start:bar_idx + 1].reset_index(drop=True)
    if len(sub) < 6:
        return out

    try:
        from mmc.context import find_context_areas, find_unusual_context

        # Aggregate across *all* areas in the window — a concept is "present" if
        # any active context area carries that defense (not just the last one).
        areas = find_context_areas(sub)
        if areas:
            defenses = {a.defense for a in areas}
            out["flod_present"] = float("FLOD" in defenses)
            out["odd_present"]  = float("ODD" in defenses)
            out["lod_only"]     = float(defenses == {"LOD"})

        # Unusual context is a *separate* detector (FVA stops offering fair value
        # and seeks liquidity) — find_context_areas only returns usual areas.
        if find_unusual_context(sub):
            out["unusual_context"] = 1.0
    except Exception:
        pass

    return out


# ---------------------------------------------------------------------------
# Entry features (ep 11–12)
# ---------------------------------------------------------------------------

def _entry_features(
    df: pd.DataFrame,
    bar_idx: int,
    look_back: int = 20,
) -> Dict[str, float]:
    """Detect sharp-turn and order-flow entry signals at ``bar_idx``."""
    out = {"sharp_turn": 0.0, "order_flow_entry": 0.0, "entry_fast": 0.0}

    start = max(0, bar_idx - look_back)
    sub = df.iloc[start:bar_idx + 1].reset_index(drop=True)
    if len(sub) < 5:
        return out

    try:
        from mmc.context import find_context_areas
        from mmc.entry.detect import find_order_flow_entries, find_sharp_turns

        contexts = find_context_areas(sub)
        for ctx in contexts:
            turns = find_sharp_turns(ctx, sub)
            if turns:
                out["sharp_turn"] = 1.0
                out["entry_fast"] = float(any(getattr(t, "fast", False) for t in turns))
            flows = find_order_flow_entries(ctx, sub)
            if flows:
                out["order_flow_entry"] = 1.0
    except Exception:
        pass

    return out


# ---------------------------------------------------------------------------
# R-to-TP feature
# ---------------------------------------------------------------------------

def _r_to_tp(
    df: pd.DataFrame,
    bar_idx: int,
    atr_period: int = 14,
) -> float:
    """Estimate the R multiple to the nearest ITH/ITL from the current bar.

    ANALYSIS.md: min_rr=2.0 is the sweet spot. We normalise by ATR so the
    network can learn this threshold directly.
    """
    sub = df.iloc[max(0, bar_idx - 60):bar_idx + 1].reset_index(drop=True)
    if len(sub) < 5:
        return 0.0

    atr = _atr(sub, atr_period)
    if atr <= 0:
        return 0.0

    swings = find_swings(sub)
    if not swings:
        return 0.0

    cur_close = float(df["close"].iloc[bar_idx])
    highs = swing_highs(swings)
    lows  = swing_lows(swings)

    # Nearest premium (high) and discount (low) above/below current price
    near_high = min(
        (s.price for s in highs if s.price > cur_close), default=None
    )
    near_low = max(
        (s.price for s in lows if s.price < cur_close), default=None
    )

    dist = None
    if near_high is not None:
        dist = near_high - cur_close
    if near_low is not None:
        d = cur_close - near_low
        dist = d if dist is None else min(dist, d)

    return (dist / atr) if dist is not None else 0.0


# ---------------------------------------------------------------------------
# SMT — ep 13 (correlated-pair divergence)
# ---------------------------------------------------------------------------

def _smt_features(
    primary_df: pd.DataFrame,
    corr_df: Optional[pd.DataFrame],
    bar_idx: int,
    look_back: int = 10,
) -> Dict[str, float]:
    """Compare swing lows (bullish SMT) or swing highs (bearish SMT) between
    two correlated instruments (ep 13: e.g. EURUSD vs GBPUSD).

    Bullish SMT: primary makes higher low while correlated makes lower low.
    Bearish SMT: primary makes lower high while correlated makes higher high.
    """
    out = {"smt_bullish": 0.0, "smt_bearish": 0.0}
    if corr_df is None or bar_idx < look_back + 2:
        return out

    p_bar = primary_df.index[bar_idx]

    # Align correlated DataFrame to same timeframe slice
    try:
        p_sub = primary_df.iloc[max(0, bar_idx - look_back):bar_idx + 1].reset_index(drop=True)
        c_sub = corr_df.loc[corr_df.index <= p_bar].tail(look_back + 1).reset_index(drop=True)

        if len(p_sub) < 3 or len(c_sub) < 3:
            return out

        p_swings = find_swings(p_sub)
        c_swings = find_swings(c_sub)

        p_lows  = swing_lows(p_swings)
        c_lows  = swing_lows(c_swings)
        p_highs = swing_highs(p_swings)
        c_highs = swing_highs(c_swings)

        # Bullish SMT: primary higher low, correlated lower low
        if len(p_lows) >= 2 and len(c_lows) >= 2:
            p_bull = p_lows[-1].price > p_lows[-2].price
            c_bull = c_lows[-1].price < c_lows[-2].price
            out["smt_bullish"] = float(p_bull and c_bull)

        # Bearish SMT: primary lower high, correlated higher high
        if len(p_highs) >= 2 and len(c_highs) >= 2:
            p_bear = p_highs[-1].price < p_highs[-2].price
            c_bear = c_highs[-1].price > c_highs[-2].price
            out["smt_bearish"] = float(p_bear and c_bear)

    except Exception:
        pass

    return out


# ---------------------------------------------------------------------------
# Market structure trend flags (ep 10)
# ---------------------------------------------------------------------------

def _structure_flags(df: pd.DataFrame, bar_idx: int, look_back: int = 40) -> Dict[str, float]:
    """Running highs → bullish, running lows → bearish (ep 10)."""
    out = {"running_highs": 0.0, "running_lows": 0.0}
    sub = df.iloc[max(0, bar_idx - look_back):bar_idx + 1].reset_index(drop=True)
    if len(sub) < 6:
        return out

    swings = find_swings(sub)
    highs = swing_highs(swings)
    lows  = swing_lows(swings)

    if len(highs) >= 2:
        out["running_highs"] = float(highs[-1].price > highs[-2].price)
    if len(lows) >= 2:
        out["running_lows"] = float(lows[-1].price < lows[-2].price)

    return out


# ---------------------------------------------------------------------------
# Master feature extractor
# ---------------------------------------------------------------------------

def extract_features(
    bar_idx: int,
    entry_df: pd.DataFrame,
    htf_df: Optional[pd.DataFrame] = None,
    corr_df: Optional[pd.DataFrame] = None,
    direction: Optional[Direction] = None,
) -> np.ndarray:
    """Extract the full feature vector for a bar at ``bar_idx`` in ``entry_df``.

    Args:
        bar_idx:   Integer position in entry_df to extract features at.
        entry_df:  Entry-timeframe OHLCV DataFrame (H1 or M15). Must have a
                   DatetimeIndex.
        htf_df:    Context-timeframe DataFrame (H4 or D1) for HTF bias features.
                   None → HTF features are 0.
        corr_df:   Correlated instrument DataFrame (same TF as entry_df) for SMT.
                   None → SMT features are 0.
        direction: Direction hint for PD array filtering. None = no filter.

    Returns:
        np.ndarray of shape (N_FEATURES,), dtype float32.
    """
    bar_time = entry_df.index[bar_idx]
    hour = bar_time.hour

    feats: Dict[str, float] = {}

    # -- Timing
    feats.update(_session_flags(hour))

    # -- HTF bias
    feats.update(_htf_bias(htf_df, bar_time))

    # -- Sweep / run / red zone / two-sting
    feats.update(_sweep_run_features(entry_df, bar_idx))

    # -- PD arrays
    feats.update(_pd_array_features(entry_df, bar_idx, direction))

    # -- Context (FLOD / ODD / unusual)
    feats.update(_context_features(entry_df, bar_idx))

    # -- Entry signals
    feats.update(_entry_features(entry_df, bar_idx))

    # -- R to TP
    feats["r_to_tp"] = min(_r_to_tp(entry_df, bar_idx), 10.0) / 10.0

    # -- SMT
    feats.update(_smt_features(entry_df, corr_df, bar_idx))

    # -- Market structure
    feats.update(_structure_flags(entry_df, bar_idx))

    return np.array([feats[k] for k in FEATURE_NAMES], dtype=np.float32)

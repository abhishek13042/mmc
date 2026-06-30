"""Batch training support: build the expensive feature dataset ONCE per
(symbol, timeframe-combo), then relabel cheaply for many take-profit targets.

The feature vector for a setup does NOT depend on where we place the take
profit — only the *label* (win/loss) does. So instead of re-running the costly
atoz precompute for every TP target, we:

  1. ``build_base`` once per (symbol, ctx_tf, entry_tf): runs FVG/atoz feature
     extraction for every mitigated FVG setup and records the trade geometry
     (entry, stop, risk, direction) plus the structural take-profit candidates
     (nearest STH/STL, ITH/ITL, buy/sell-side liquidity pool).  Cached to pkl.

  2. ``label_for_mode`` derives the win/loss labels + per-setup realised RR for
     one TP target (rr2/rr3/rr4/sth/ith/liq) by forward-simulating from the
     already-cached geometry.  Cheap — no atoz recompute.

TP targets (ep-faithful):
  * rr2/rr3/rr4 — fixed reward:risk multiple.
  * sth/stl     — nearest short-term high (bullish) / low (bearish): a swing
                  followed by an FVG (mmc.core.short_term_points).
  * ith/itl     — nearest intermediate-term high/low (mmc.core.intermediate_term_points).
  * liq         — nearest BUY-side liquidity pool above (bullish) / SELL-side
                  pool below (bearish) (atoz.liquidity.find_liquidity_pools):
                  buy-side liquidity rests above old highs, sell-side below lows.
"""

from __future__ import annotations

import os
import pickle
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from mmc.core import (
    Direction,
    StructurePointType,
    find_fvgs,
    find_swings,
    intermediate_term_points,
    mark_mitigation,
    short_term_points,
)
from mmc.core.types import Timeframe
from mmc.data import load

from mmc.brain.atoz_features import AtozSignals
from mmc.brain.features_v2 import FEATURE_NAMES_V2, extract_features_v2
from mmc.brain.labels import label_trade

_SMT_PAIRS = {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD", "XAUUSD": None}

CONTEXT_LOOKBACK = 40
MAX_FWD_BARS = 200

TP_MODES = ["rr2", "rr3", "rr4", "sth", "ith", "liq"]
_FIXED_RR = {"rr2": 2.0, "rr3": 3.0, "rr4": 4.0}

# geometry / bookkeeping columns stored alongside the 55 feature columns
GEOM_COLS = [
    "entry_bar", "entry_time", "symbol", "dir_sign",
    "entry_price", "stop", "risk",
    "tp_sth", "tp_ith", "tp_liq",
]


def _atr_series(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    tr = (df["high"] - df["low"]).abs()
    return tr.rolling(period, min_periods=1).mean().to_numpy()


# --------------------------------------------------------------------------- #
# Structural take-profit candidates
# --------------------------------------------------------------------------- #

def _structural_targets(entry_df: pd.DataFrame):
    """Return (idx, price) arrays for each structural target family, split by
    whether the level is a HIGH (a bullish-trade target, sits above) or a LOW
    (a bearish-trade target, sits below)."""
    swings = find_swings(entry_df)
    fvgs = find_fvgs(entry_df)

    sth = short_term_points(swings, fvgs)
    ith = intermediate_term_points(swings)

    def _split(points, high_types, low_types):
        hi = [(p.index, p.price) for p in points if p.kind in high_types]
        lo = [(p.index, p.price) for p in points if p.kind in low_types]
        hi_idx = np.array([i for i, _ in hi], dtype=np.int64) if hi else np.empty(0, np.int64)
        hi_px = np.array([p for _, p in hi], dtype=np.float64) if hi else np.empty(0)
        lo_idx = np.array([i for i, _ in lo], dtype=np.int64) if lo else np.empty(0, np.int64)
        lo_px = np.array([p for _, p in lo], dtype=np.float64) if lo else np.empty(0)
        return (hi_idx, hi_px), (lo_idx, lo_px)

    sth_hi, sth_lo = _split(
        sth, {StructurePointType.STH}, {StructurePointType.STL}
    )
    ith_hi, ith_lo = _split(
        ith, {StructurePointType.ITH}, {StructurePointType.ITL}
    )

    # liquidity pools (atoz): highs = buy-side, lows = sell-side
    liq_hi = (np.empty(0, np.int64), np.empty(0))
    liq_lo = (np.empty(0, np.int64), np.empty(0))
    try:
        from atoz.liquidity import find_liquidity_pools, PoolType
        pools = find_liquidity_pools(entry_df)
        hi = [(p.index, p.price) for p in pools
              if p.kind in (PoolType.EQUAL_HIGHS, PoolType.SINGLE_HIGH)]
        lo = [(p.index, p.price) for p in pools
              if p.kind in (PoolType.EQUAL_LOWS, PoolType.SINGLE_LOW)]
        if hi:
            liq_hi = (np.array([i for i, _ in hi], np.int64),
                      np.array([p for _, p in hi], np.float64))
        if lo:
            liq_lo = (np.array([i for i, _ in lo], np.int64),
                      np.array([p for _, p in lo], np.float64))
    except Exception:
        pass

    return {
        "sth": (sth_hi, sth_lo),
        "ith": (ith_hi, ith_lo),
        "liq": (liq_hi, liq_lo),
    }


def _nearest_target(idx_arr, px_arr, bar: int, entry: float, above: bool) -> float:
    """Nearest target level formed BEFORE ``bar`` that sits above (bullish) or
    below (bearish) ``entry``.  Returns NaN if none qualifies."""
    if idx_arr.size == 0:
        return float("nan")
    mask = idx_arr < bar
    if not mask.any():
        return float("nan")
    px = px_arr[mask]
    if above:
        cand = px[px > entry]
        return float(cand.min()) if cand.size else float("nan")
    else:
        cand = px[px < entry]
        return float(cand.max()) if cand.size else float("nan")


# --------------------------------------------------------------------------- #
# Base dataset (features + geometry + structural TPs), built once, cached
# --------------------------------------------------------------------------- #

def build_base(
    symbol: str,
    ctx_tf: Timeframe,
    entry_tf: Timeframe,
    cache_path: Optional[str] = None,
    log=print,
) -> pd.DataFrame:
    """Build (or load) the per-setup feature + geometry table for one TF combo."""
    if cache_path and os.path.exists(cache_path):
        log(f"    [base cache] {os.path.basename(cache_path)}")
        return pickle.load(open(cache_path, "rb"))

    entry_df = load(symbol, entry_tf)
    htf_df = load(symbol, ctx_tf)
    corr_sym = _SMT_PAIRS.get(symbol)
    corr_df = load(corr_sym, entry_tf) if corr_sym else None

    n = len(entry_df)
    log(f"    [base build] {symbol} {ctx_tf.name}->{entry_tf.name}: {n:,} bars")
    log(f"    precomputing atoz signals (one time)...")
    atoz_signals = AtozSignals.precompute(entry_df, htf_df=htf_df)

    fvgs = find_fvgs(entry_df)
    mark_mitigation(entry_df, fvgs)
    atr = _atr_series(entry_df)

    log(f"    precomputing structural TP candidates...")
    targets = _structural_targets(entry_df)

    rows: List[Dict] = []
    for fvg in fvgs:
        bar = getattr(fvg, "mitigation_index", None)
        if bar is None or not getattr(fvg, "mitigated", False):
            continue
        if bar < CONTEXT_LOOKBACK or bar >= n - MAX_FWD_BARS:
            continue

        buf = atr[bar] * 0.1 if atr[bar] > 0 else 0.0
        bullish = fvg.direction is Direction.BULLISH
        if bullish:
            entry = fvg.top
            stop = fvg.bottom - buf
            risk = entry - stop
        else:
            entry = fvg.bottom
            stop = fvg.top + buf
            risk = stop - entry
        if risk <= 0:
            continue

        # structural TPs
        tps = {}
        for fam in ("sth", "ith", "liq"):
            hi, lo = targets[fam]
            if bullish:
                tps[fam] = _nearest_target(hi[0], hi[1], bar, entry, above=True)
            else:
                tps[fam] = _nearest_target(lo[0], lo[1], bar, entry, above=False)

        feats = extract_features_v2(
            bar, entry_df, atoz_signals,
            htf_df=htf_df, corr_df=corr_df, direction=fvg.direction,
        )
        row = {k: float(feats[i]) for i, k in enumerate(FEATURE_NAMES_V2)}
        row.update({
            "entry_bar": bar,
            "entry_time": entry_df.index[bar],
            "symbol": symbol,
            "dir_sign": 1 if bullish else -1,
            "entry_price": float(entry),
            "stop": float(stop),
            "risk": float(risk),
            "tp_sth": tps["sth"],
            "tp_ith": tps["ith"],
            "tp_liq": tps["liq"],
        })
        rows.append(row)

    base = pd.DataFrame(rows).reset_index(drop=True)
    log(f"    [base built] {len(base):,} setups")
    if cache_path and not base.empty:
        pickle.dump(base, open(cache_path, "wb"))
    return base


# --------------------------------------------------------------------------- #
# Cheap relabelling per TP mode
# --------------------------------------------------------------------------- #

def label_for_mode(
    base: pd.DataFrame,
    entry_df: pd.DataFrame,
    mode: str,
    max_rr: float = 10.0,
    min_rr: float = 0.5,
) -> pd.DataFrame:
    """Return a copy of ``base`` with ``label`` (1/0) and ``rr`` (realised
    reward:risk of the TARGET) columns added for ``mode``; setups with no valid
    target for this mode are dropped.

    For structural modes (sth/ith/liq) the target RR is clamped to
    ``[min_rr, max_rr]`` — a target closer than ``min_rr`` or further than
    ``max_rr`` is unrealistic and the setup is dropped, which keeps a few
    extreme 'lotto-ticket' liquidity targets from dominating the labels."""
    out = base.copy()
    labels: List[Optional[float]] = []
    rrs: List[float] = []

    fixed = _FIXED_RR.get(mode)
    tp_col = {"sth": "tp_sth", "ith": "tp_ith", "liq": "tp_liq"}.get(mode)

    for _, r in base.iterrows():
        entry = r["entry_price"]; stop = r["stop"]; risk = r["risk"]
        bullish = r["dir_sign"] > 0
        bar = int(r["entry_bar"])

        if fixed is not None:
            tp = entry + fixed * risk if bullish else entry - fixed * risk
            rr = fixed
        else:
            tp = r[tp_col]
            if not np.isfinite(tp):
                labels.append(None); rrs.append(float("nan")); continue
            rr = abs(tp - entry) / risk if risk > 0 else 0.0
            if rr < min_rr or rr > max_rr:
                labels.append(None); rrs.append(float("nan")); continue

        lbl = label_trade(entry, stop, tp, entry_df, bar, max_bars=MAX_FWD_BARS)
        labels.append(lbl)
        rrs.append(rr)

    out["label"] = labels
    out["rr"] = rrs
    out = out[out["label"].notna()].reset_index(drop=True)
    out["label"] = out["label"].astype(float)
    return out

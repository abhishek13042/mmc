"""Dataset generator for the MMC brain.

Philosophy (per user): take EVERY possible MMC setup, not just the strict
rule-engine entries. A "setup" = any point where price taps a PD array (a fair
value gap) — the core MMC entry premise. At each tap we:

    1. Define the trade  — direction from the array polarity, entry at the near
       edge, stop beyond the array, target the nearest opposing liquidity
       (ITH/ITL) or a 2R fallback.
    2. Detect which concepts are PRESENT  — the 31-feature vector (killzone,
       sweep/run, HTF bias, FLOD/ODD, SMT, red zone, …). Present-or-not, plus
       a few graded scores.
    3. Label the outcome  — simulate forward: did TP hit before SL?

The neural network then learns how much WEIGHT each present concept contributes
to a winning setup. We do NOT hard-filter by RR — r_to_tp is a *feature*, so the
net learns the min-RR threshold itself (ANALYSIS.md: 2.0 sweet spot).

Result: a DataFrame, one row per tapped PD array:
    31 feature columns + label + entry_bar + entry_time + symbol
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from mmc.brain.features import FEATURE_NAMES, extract_features
from mmc.brain.labels import label_trade
from mmc.core import (
    Direction,
    find_fvgs,
    find_swings,
    mark_mitigation,
    swing_highs,
    swing_lows,
)
from mmc.core.types import Timeframe
from mmc.data import load

# Correlated pairs for SMT (ep 13)
_SMT_PAIRS: Dict[str, Optional[str]] = {
    "EURUSD": "GBPUSD",
    "GBPUSD": "EURUSD",
    "XAUUSD": None,
}

# Skip candidates within this many bars of the data start (need look-back history)
CONTEXT_LOOKBACK = 40


def _atr_series(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    """Simple ATR (rolling mean true-range) as a numpy array aligned to df."""
    tr = (df["high"] - df["low"]).abs()
    return tr.rolling(period, min_periods=1).mean().to_numpy()


def build_dataset(
    symbol: str,
    context_tf: Timeframe = Timeframe.H4,
    entry_tf: Timeframe = Timeframe.H1,
    max_bars: int = 200,
    limit_bars: Optional[int] = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """Build the feature+label dataset for one symbol.

    Args:
        symbol:     Instrument, e.g. "EURUSD".
        context_tf: HTF for bias context (D1 or H4).
        entry_tf:   LTF where setups are detected (H1 or M15).
        max_bars:   Forward simulation window for labelling.
        limit_bars: If set, use only the last N entry-TF bars (faster first run).
        verbose:    Print progress.

    Returns:
        DataFrame with FEATURE_NAMES + ["label", "entry_bar", "entry_time",
        "symbol"].
    """
    entry_df = load(symbol, entry_tf)
    htf_df   = load(symbol, context_tf)

    if limit_bars is not None and len(entry_df) > limit_bars:
        entry_df = entry_df.tail(limit_bars)

    corr_sym = _SMT_PAIRS.get(symbol)
    corr_df  = load(corr_sym, entry_tf) if corr_sym else None

    n = len(entry_df)
    if verbose:
        print(f"[brain] {symbol} {context_tf.name}->{entry_tf.name}: {n} bars")

    # --- Detect all PD arrays once over the whole window ----------------------
    fvgs = find_fvgs(entry_df)
    mark_mitigation(entry_df, fvgs)
    swings = find_swings(entry_df)
    highs  = swing_highs(swings)
    lows   = swing_lows(swings)
    atr    = _atr_series(entry_df)

    rows: List[Dict] = []
    n_candidates = 0

    for f in fvgs:
        # A setup = price taps (mitigates) the fair value gap
        bar = getattr(f, "mitigation_index", None)
        if bar is None or not getattr(f, "mitigated", False):
            continue
        if bar < CONTEXT_LOOKBACK or bar >= n - max_bars:
            continue

        buf = atr[bar] * 0.1 if atr[bar] > 0 else 0.0

        if f.direction is Direction.BULLISH:
            entry = f.top
            stop  = f.bottom - buf
            risk  = entry - stop
            if risk <= 0:
                continue
            targets = [s.price for s in highs if s.index < bar and s.price > entry]
            tp = min(targets) if targets else entry + 2.0 * risk
        else:
            entry = f.bottom
            stop  = f.top + buf
            risk  = stop - entry
            if risk <= 0:
                continue
            targets = [s.price for s in lows if s.index < bar and s.price < entry]
            tp = max(targets) if targets else entry - 2.0 * risk

        n_candidates += 1

        label = label_trade(entry, stop, tp, entry_df, bar, max_bars=max_bars)
        if label is None:
            continue  # neither TP nor SL hit within window — drop

        feats = extract_features(
            bar, entry_df, htf_df=htf_df, corr_df=corr_df, direction=f.direction
        )
        row = {k: float(feats[i]) for i, k in enumerate(FEATURE_NAMES)}
        row["label"]      = label
        row["entry_bar"]  = bar
        row["entry_time"] = entry_df.index[bar]
        row["symbol"]     = symbol
        rows.append(row)

    if not rows:
        if verbose:
            print(f"[brain] {symbol}: 0 labeled setups "
                  f"({n_candidates} candidates, all timed out)")
        return pd.DataFrame()

    df_out = pd.DataFrame(rows).reset_index(drop=True)
    if verbose:
        wins  = int(df_out["label"].sum())
        total = len(df_out)
        print(f"[brain] {symbol}: {total} setups "
              f"({n_candidates} taps), {wins} wins "
              f"({100*wins/total:.1f}%), {total-wins} losses")
    return df_out


def build_all_datasets(
    symbols: List[str] = ("EURUSD", "GBPUSD", "XAUUSD"),
    context_tf: Timeframe = Timeframe.H4,
    entry_tf: Timeframe = Timeframe.H1,
    **kwargs,
) -> pd.DataFrame:
    """Build and concatenate datasets for all symbols."""
    parts = [build_dataset(s, context_tf, entry_tf, **kwargs) for s in symbols]
    dfs = [p for p in parts if not p.empty]
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)

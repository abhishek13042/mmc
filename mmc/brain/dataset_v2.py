"""Brain v2 dataset builder: same FVG-tap candidate universe as v1, but each row
carries the combined mmc+atoz feature vector (55 features).

The candidate definition is identical to v1 (``dataset.py``) — every *mitigated*
fair value gap is one setup, the trade is defined from the array, and the label
comes from forward simulation — so v1 and v2 are compared on the SAME setups and
the SAME labels. Only the feature columns differ, which isolates the effect of
adding the atoz knowledge base.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from mmc.brain.atoz_features import AtozSignals
from mmc.brain.features_v2 import FEATURE_NAMES_V2, extract_features_v2
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

_SMT_PAIRS: Dict[str, Optional[str]] = {
    "EURUSD": "GBPUSD",
    "GBPUSD": "EURUSD",
    "XAUUSD": None,
}

CONTEXT_LOOKBACK = 40


def _atr_series(df: pd.DataFrame, period: int = 14) -> np.ndarray:
    tr = (df["high"] - df["low"]).abs()
    return tr.rolling(period, min_periods=1).mean().to_numpy()


def build_dataset_v2(
    symbol: str,
    context_tf: Timeframe = Timeframe.H4,
    entry_tf: Timeframe = Timeframe.H1,
    max_bars: int = 200,
    limit_bars: Optional[int] = None,
    target_rr: Optional[float] = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """Build the v2 feature+label dataset for one symbol (mmc+atoz features).

    ``target_rr``: if set, all TPs are placed at ``entry ± target_rr * risk``
    (fixed RR).  If None, TP is the nearest historical swing (variable RR,
    default behaviour).
    """
    entry_df = load(symbol, entry_tf)
    htf_df = load(symbol, context_tf)

    if limit_bars is not None and len(entry_df) > limit_bars:
        entry_df = entry_df.tail(limit_bars)

    corr_sym = _SMT_PAIRS.get(symbol)
    corr_df = load(corr_sym, entry_tf) if corr_sym else None

    n = len(entry_df)
    if verbose:
        print(f"[brain-v2] {symbol} {context_tf.name}->{entry_tf.name}: {n} bars")
        print(f"[brain-v2] precomputing atoz signals...")

    # ONE atoz precompute pass for the whole entry timeframe + HTF
    atoz_signals = AtozSignals.precompute(entry_df, htf_df=htf_df)

    fvgs = find_fvgs(entry_df)
    mark_mitigation(entry_df, fvgs)
    swings = find_swings(entry_df)
    highs = swing_highs(swings)
    lows = swing_lows(swings)
    atr = _atr_series(entry_df)

    rows: List[Dict] = []
    n_candidates = 0

    for fvg in fvgs:
        bar = getattr(fvg, "mitigation_index", None)
        if bar is None or not getattr(fvg, "mitigated", False):
            continue
        if bar < CONTEXT_LOOKBACK or bar >= n - max_bars:
            continue

        buf = atr[bar] * 0.1 if atr[bar] > 0 else 0.0

        if fvg.direction is Direction.BULLISH:
            entry = fvg.top
            stop = fvg.bottom - buf
            risk = entry - stop
            if risk <= 0:
                continue
            if target_rr is not None:
                tp = entry + target_rr * risk
            else:
                targets = [s.price for s in highs if s.index < bar and s.price > entry]
                tp = min(targets) if targets else entry + 2.0 * risk
        else:
            entry = fvg.bottom
            stop = fvg.top + buf
            risk = stop - entry
            if risk <= 0:
                continue
            if target_rr is not None:
                tp = entry - target_rr * risk
            else:
                targets = [s.price for s in lows if s.index < bar and s.price < entry]
                tp = max(targets) if targets else entry - 2.0 * risk

        n_candidates += 1

        label = label_trade(entry, stop, tp, entry_df, bar, max_bars=max_bars)
        if label is None:
            continue

        feats = extract_features_v2(
            bar, entry_df, atoz_signals,
            htf_df=htf_df, corr_df=corr_df, direction=fvg.direction,
        )
        row = {k: float(feats[i]) for i, k in enumerate(FEATURE_NAMES_V2)}
        row["label"] = label
        row["entry_bar"] = bar
        row["entry_time"] = entry_df.index[bar]
        row["symbol"] = symbol
        rows.append(row)

    if not rows:
        if verbose:
            print(f"[brain-v2] {symbol}: 0 labeled setups ({n_candidates} candidates)")
        return pd.DataFrame()

    df_out = pd.DataFrame(rows).reset_index(drop=True)
    if verbose:
        wins = int(df_out["label"].sum())
        total = len(df_out)
        print(f"[brain-v2] {symbol}: {total} setups ({n_candidates} taps), "
              f"{wins} wins ({100 * wins / total:.1f}%), {total - wins} losses")
    return df_out


def build_all_datasets_v2(
    symbols: List[str] = ("EURUSD", "GBPUSD", "XAUUSD"),
    context_tf: Timeframe = Timeframe.H4,
    entry_tf: Timeframe = Timeframe.H1,
    **kwargs,
) -> pd.DataFrame:
    """Build and concatenate v2 datasets for all symbols."""
    parts = [build_dataset_v2(s, context_tf, entry_tf, **kwargs) for s in symbols]
    dfs = [p for p in parts if not p.empty]
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)

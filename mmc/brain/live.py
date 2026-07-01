"""Live inference for the MMC brain — SAME code path as the backtest.

`LiveBrain.evaluate(entry_df, htf_df, corr_df)` runs the identical setup
detection and feature extraction used by `batch.build_base` (mitigated FVG ->
55-feature vector -> trained perceptron), but only reports a signal when the
**most recently closed bar** is the mitigation bar. Because it reuses
`find_fvgs` / `mark_mitigation` / `extract_features_v2` and the trained `.pt`
weights, a setup fired live is identical to the one the backtest would label.

This module has NO broker dependency — it is pure model inference. The MT5 robot
(`examples/mt5_live_robot.py`) feeds it DataFrames and acts on the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import torch

from mmc.core import (
    Direction,
    find_fvgs,
    find_swings,
    mark_mitigation,
)
from mmc.brain.architectures import get_model
from mmc.brain.atoz_features import AtozSignals
from mmc.brain.features_v2 import FEATURE_NAMES_V2, extract_features_v2

CONTEXT_LOOKBACK = 40         # same guard as batch.build_base


@dataclass
class Signal:
    direction: int            # 1 long, -1 short
    entry: float
    stop: float
    tp: float
    risk: float
    score: float              # model probability 0..1
    rr: float
    bar_time: pd.Timestamp


class LiveBrain:
    """Loads one trained perceptron and scores the latest bar's setup, if any."""

    def __init__(
        self,
        weights_pt: str,
        target_rr: float = 4.0,
        threshold: float = 0.50,
        sl_buffer_atr: float = 0.1,
        atr_period: int = 14,
    ):
        self.model = get_model("perceptron", n_features=len(FEATURE_NAMES_V2))
        self.model.load_state_dict(torch.load(weights_pt, map_location="cpu"))
        self.model.eval()
        self.target_rr = target_rr
        self.threshold = threshold
        self.sl_buffer_atr = sl_buffer_atr
        self.atr_period = atr_period

    # ---------------------------------------------------------------- helpers
    def _atr(self, df: pd.DataFrame) -> np.ndarray:
        tr = (df["high"] - df["low"]).abs()
        return tr.rolling(self.atr_period, min_periods=1).mean().to_numpy()

    def _score_bar(self, bar, entry_df, atoz_signals, htf_df, corr_df, direction):
        feats = extract_features_v2(
            bar, entry_df, atoz_signals,
            htf_df=htf_df, corr_df=corr_df, direction=direction,
        )
        x = torch.tensor(np.asarray(feats, dtype=np.float32)).unsqueeze(0)
        with torch.no_grad():
            return float(torch.sigmoid(self.model(x)).item())

    # ---------------------------------------------------------------- evaluate
    def evaluate(
        self,
        entry_df: pd.DataFrame,
        htf_df: pd.DataFrame,
        corr_df: Optional[pd.DataFrame] = None,
        only_last_bar: bool = True,
    ) -> Optional[Signal]:
        """Return a Signal if the most recently CLOSED bar mitigated an FVG and
        the model score clears the threshold; else None.

        ``entry_df`` must end at the last CLOSED bar (drop the still-forming one
        before calling)."""
        n = len(entry_df)
        if n < CONTEXT_LOOKBACK + 5:
            return None

        fvgs = find_fvgs(entry_df)
        mark_mitigation(entry_df, fvgs)
        find_swings(entry_df)                 # warms internal caches; parity w/ build_base
        atr = self._atr(entry_df)
        atoz_signals = AtozSignals.precompute(entry_df, htf_df=htf_df)

        last = n - 1
        best: Optional[Signal] = None

        for fvg in fvgs:
            bar = getattr(fvg, "mitigation_index", None)
            if bar is None or not getattr(fvg, "mitigated", False):
                continue
            if bar < CONTEXT_LOOKBACK:
                continue
            if only_last_bar and bar != last:
                continue

            buf = atr[bar] * self.sl_buffer_atr if atr[bar] > 0 else 0.0
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

            score = self._score_bar(bar, entry_df, atoz_signals, htf_df, corr_df, fvg.direction)
            if score < self.threshold:
                continue

            tp = entry + self.target_rr * risk if bullish else entry - self.target_rr * risk
            sig = Signal(
                direction=1 if bullish else -1,
                entry=float(entry), stop=float(stop), tp=float(tp),
                risk=float(risk), score=float(score), rr=float(self.target_rr),
                bar_time=entry_df.index[bar],
            )
            # if several gaps mitigate on the same bar, keep the highest score
            if best is None or sig.score > best.score:
                best = sig

        return best

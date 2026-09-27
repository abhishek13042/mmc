"""Robustness layer — the metrics that actually validate "is this edge real".

1. In-sample vs out-of-sample decay. The 72-model training matrix recorded each
   strategy's *in-sample* (train/test-split) WR/PF/ExpR in
   ``mmc/brain/weights/RESULTS_TABLE.csv``. This log is the *out-of-sample*
   live-forward read. A big PF/ExpR drop from IS to OOS is the classic overfit
   red flag.

2. Monte Carlo trade-shuffle. Reshuffling trade ORDER (bootstrap on the same
   trades) gives a distribution of possible equity curves and, crucially, of
   max-drawdowns — so you learn whether your one observed drawdown was
   luckily-shallow or representative of the tail.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from mmc.evaluation.metrics.drawdown import equity_curve_r, _underwater

# Located next to the trained weights: mmc/brain/weights/RESULTS_TABLE.csv.
# __file__ = mmc/evaluation/metrics/robustness.py -> up 3 = the `mmc` package.
_MMC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_RESULTS_TABLE = os.path.join(_MMC_DIR, "brain", "weights", "RESULTS_TABLE.csv")


# --------------------------------------------------------------------------- #
# In-sample vs out-of-sample decay
# --------------------------------------------------------------------------- #

@dataclass
class ISOOSDecay:
    is_pf: Optional[float]
    oos_pf: float
    pf_decay: Optional[float]        # (is_pf - oos_pf) / is_pf, fraction
    is_exp_r: Optional[float]
    oos_exp_r: float
    exp_r_decay: Optional[float]
    is_win_rate: Optional[float]
    oos_win_rate: float

    def as_dict(self) -> Dict[str, float]:
        return {
            "is_pf": self.is_pf, "oos_pf": self.oos_pf, "pf_decay": self.pf_decay,
            "is_exp_r": self.is_exp_r, "oos_exp_r": self.oos_exp_r,
            "exp_r_decay": self.exp_r_decay,
            "is_win_rate": self.is_win_rate, "oos_win_rate": self.oos_win_rate,
        }


def load_results_table(path: str = DEFAULT_RESULTS_TABLE) -> Optional[pd.DataFrame]:
    """Load the in-sample baseline table, or ``None`` if it's not present."""
    if not os.path.exists(path):
        return None
    return pd.read_csv(path)


def is_baseline_for(
    strategy_id: str,
    table: Optional[pd.DataFrame],
) -> Optional[pd.Series]:
    """Look up the IS row for a strategy_id like "EURUSD_H4_H1_rr4".

    ``mode`` in the table is the TP mode (rr2/rr3/rr4/sth/ith/liq); the fleet
    rr maps directly (rr=4 -> mode "rr4").
    """
    if table is None:
        return None
    parts = strategy_id.split("_")
    try:
        pair = parts[0]
        rr_tok = parts[-1].lower()                    # "rr4"
        mode = rr_tok if rr_tok.startswith("rr") else "rr" + rr_tok.rstrip("r")
        combo = "_".join(parts[1:-1])
    except Exception:
        return None
    m = table[
        (table["pair"] == pair)
        & (table["combo"] == combo)
        & (table["mode"] == mode)
    ]
    return m.iloc[0] if len(m) else None


def is_oos_decay(
    strategy_id: str,
    oos_r: np.ndarray,
    table: Optional[pd.DataFrame],
) -> ISOOSDecay:
    oos_r = np.asarray(oos_r, dtype=float)
    gp = oos_r[oos_r > 0].sum(); gl = -oos_r[oos_r < 0].sum()
    oos_pf = float(gp / gl) if gl > 0 else (float("inf") if gp > 0 else 0.0)
    oos_exp = float(oos_r.mean()) if oos_r.size else 0.0
    oos_wr = float((oos_r > 0).mean()) if oos_r.size else 0.0

    row = is_baseline_for(strategy_id, table)
    if row is None:
        return ISOOSDecay(None, oos_pf, None, None, oos_exp, None, None, oos_wr)

    is_pf = float(row["pf"]); is_exp = float(row["exp_r"]); is_wr = float(row["win_rate"])
    pf_decay = (is_pf - oos_pf) / is_pf if is_pf > 0 else None
    exp_decay = (is_exp - oos_exp) / is_exp if is_exp != 0 else None
    return ISOOSDecay(is_pf, oos_pf, pf_decay, is_exp, oos_exp, exp_decay, is_wr, oos_wr)


# --------------------------------------------------------------------------- #
# Monte Carlo trade-order shuffle
# --------------------------------------------------------------------------- #

@dataclass
class MonteCarlo:
    n_iters: int
    observed_max_dd_r: float
    dd_median: float
    dd_p95: float                    # 95th-percentile max drawdown across shuffles
    dd_worst: float
    prob_worse_than_observed: float  # P(shuffle DD > observed) — low = you got lucky
    final_r_p5: float                # 5th-pct terminal equity (R)
    final_r_median: float
    curves: Optional[np.ndarray] = None   # (k, n) sample of equity curves for plotting

    def as_dict(self) -> Dict[str, float]:
        return {
            "mc_iters": self.n_iters,
            "mc_observed_max_dd_r": self.observed_max_dd_r,
            "mc_dd_median": self.dd_median,
            "mc_dd_p95": self.dd_p95,
            "mc_dd_worst": self.dd_worst,
            "mc_prob_worse_than_observed": self.prob_worse_than_observed,
            "mc_final_r_p5": self.final_r_p5,
            "mc_final_r_median": self.final_r_median,
        }


def _max_dd(equity_2d: np.ndarray) -> np.ndarray:
    """Vectorised max drawdown (R) for each row of a (k, n) equity matrix."""
    peak = np.maximum.accumulate(equity_2d, axis=1)
    return (peak - equity_2d).max(axis=1)


def monte_carlo(
    r: np.ndarray,
    iters: int = 1000,
    seed: int = 12345,
    keep_curves: int = 100,
) -> MonteCarlo:
    """Reshuffle trade order ``iters`` times; report the drawdown distribution.

    Uses permutation (not resampling) so every shuffle has the same trade set
    and terminal equity — isolating *sequence risk*: how bad the drawdown could
    have been with the same trades in a different order.
    """
    r = np.asarray(r, dtype=float)
    n = r.size
    if n == 0:
        return MonteCarlo(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, None)

    observed_dd = float(_underwater(equity_curve_r(r))[0].max())

    rng = np.random.default_rng(seed)
    # Build (iters, n) permuted-R matrix.
    perm = np.argsort(rng.random((iters, n)), axis=1)
    shuffled = r[perm]
    equity = np.cumsum(shuffled, axis=1)

    dds = _max_dd(equity)
    finals = equity[:, -1]

    curves = None
    if keep_curves and keep_curves > 0:
        curves = equity[: min(keep_curves, iters)]

    return MonteCarlo(
        n_iters=iters,
        observed_max_dd_r=observed_dd,
        dd_median=float(np.median(dds)),
        dd_p95=float(np.percentile(dds, 95)),
        dd_worst=float(dds.max()),
        prob_worse_than_observed=float((dds > observed_dd).mean()),
        final_r_p5=float(np.percentile(finals, 5)),
        final_r_median=float(np.median(finals)),
        curves=curves,
    )

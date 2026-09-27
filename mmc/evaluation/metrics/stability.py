"""Stability / consistency layer.

Is the equity curve smooth, or is all the return from two outlier months? We
split the trade history into calendar-quarter buckets and recompute WR/PF per
bucket, and characterise the R-distribution's shape (skew, kurtosis). Positive
skew is good (many small losses, few big wins); high kurtosis warns of fat-tail
blow-up risk hiding under a nice average.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

try:  # scipy is a soft dep; fall back to moment formulas.
    from scipy.stats import skew as _scipy_skew, kurtosis as _scipy_kurtosis
    _HAVE_SCIPY = True
except Exception:  # pragma: no cover
    _HAVE_SCIPY = False


@dataclass
class BucketStat:
    label: str
    n: int
    win_rate: float
    profit_factor: float
    total_r: float


@dataclass
class StabilityMetrics:
    skew: float
    kurtosis: float                 # excess kurtosis (normal == 0)
    buckets: List[BucketStat] = field(default_factory=list)
    concentration: float = 0.0      # share of total positive R from the single
                                    #   best bucket (1.0 == all from one quarter)

    def as_dict(self) -> Dict[str, float]:
        return {
            "skew": self.skew,
            "kurtosis": self.kurtosis,
            "concentration": self.concentration,
            "n_buckets": len(self.buckets),
        }


def skewness(r: np.ndarray) -> float:
    r = np.asarray(r, dtype=float)
    if r.size < 3:
        return 0.0
    if _HAVE_SCIPY:
        return float(_scipy_skew(r, bias=False))
    m = r.mean(); sd = r.std(ddof=0)
    if sd == 0:
        return 0.0
    return float(np.mean(((r - m) / sd) ** 3))


def excess_kurtosis(r: np.ndarray) -> float:
    r = np.asarray(r, dtype=float)
    if r.size < 4:
        return 0.0
    if _HAVE_SCIPY:
        return float(_scipy_kurtosis(r, fisher=True, bias=False))
    m = r.mean(); sd = r.std(ddof=0)
    if sd == 0:
        return 0.0
    return float(np.mean(((r - m) / sd) ** 4) - 3.0)


def _pf(r: np.ndarray) -> float:
    gp = r[r > 0].sum(); gl = -r[r < 0].sum()
    if gl <= 0:
        return float("inf") if gp > 0 else 0.0
    return float(gp / gl)


def compute(r: np.ndarray, entry_times: Optional[pd.Series] = None) -> StabilityMetrics:
    """Skew/kurtosis always; per-quarter buckets when timestamps are given."""
    r = np.asarray(r, dtype=float)
    buckets: List[BucketStat] = []
    concentration = 0.0

    if entry_times is not None and len(entry_times) == r.size and r.size:
        s = pd.DataFrame({"r": r, "t": pd.to_datetime(pd.Series(entry_times).values)})
        s["bucket"] = s["t"].dt.to_period("Q").astype(str)
        pos_by_bucket = {}
        for label, g in s.groupby("bucket", sort=True):
            rr = g["r"].to_numpy()
            wins = int((rr > 0).sum())
            buckets.append(BucketStat(
                label=label,
                n=int(rr.size),
                win_rate=wins / rr.size if rr.size else 0.0,
                profit_factor=_pf(rr),
                total_r=float(rr.sum()),
            ))
            pos_by_bucket[label] = float(rr[rr > 0].sum())
        total_pos = sum(pos_by_bucket.values())
        if total_pos > 0:
            concentration = max(pos_by_bucket.values()) / total_pos

    return StabilityMetrics(
        skew=skewness(r),
        kurtosis=excess_kurtosis(r),
        buckets=buckets,
        concentration=concentration,
    )

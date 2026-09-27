"""Risk-adjusted return layer.

For a positive-skew, capped-downside R-multiple strategy (many -1R losses, a few
+4R wins) the Sharpe ratio is misleading — it penalises the big upside wins as
"volatility". Sortino (downside deviation only) and Calmar (drawdown-anchored)
fit far better, which is exactly why CTA/systematic-fund evaluation leans on
them. Sharpe is reported for reference only.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict

import numpy as np

from mmc.evaluation.metrics.drawdown import equity_curve_r, _underwater


@dataclass
class RiskAdjMetrics:
    sharpe: float
    sortino: float
    calmar: float

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)


def sharpe(r: np.ndarray) -> float:
    """Per-trade Sharpe = mean(R) / std(R). Reference only (penalises upside)."""
    r = np.asarray(r, dtype=float)
    if r.size < 2:
        return 0.0
    sd = r.std(ddof=1)
    return float(r.mean() / sd) if sd > 0 else 0.0


def sortino(r: np.ndarray) -> float:
    """Per-trade Sortino = mean(R) / downside_deviation.

    Downside deviation uses only negative R relative to a 0R target (breakeven).
    ``inf`` if there is edge but no downside at all.
    """
    r = np.asarray(r, dtype=float)
    if r.size == 0:
        return 0.0
    downside = np.minimum(r, 0.0)
    dd = np.sqrt(np.mean(np.square(downside)))
    mean = float(r.mean())
    if dd <= 0:
        return float("inf") if mean > 0 else 0.0
    return mean / dd


def calmar(r: np.ndarray, trades_per_year: float = 252.0) -> float:
    """Calmar = annualised total-R / max drawdown (R).

    Annualises the per-trade expectancy by ``trades_per_year`` so the ratio is
    comparable to the fund-world convention (annual return / max DD). ``inf`` if
    there is no drawdown.
    """
    r = np.asarray(r, dtype=float)
    n = r.size
    if n == 0:
        return 0.0
    equity = equity_curve_r(r)
    dd, _ = _underwater(equity)
    max_dd = float(dd.max())
    annual_r = float(r.mean()) * trades_per_year
    if max_dd <= 0:
        return float("inf") if annual_r > 0 else 0.0
    return annual_r / max_dd


def compute(r: np.ndarray, trades_per_year: float = 252.0) -> RiskAdjMetrics:
    return RiskAdjMetrics(
        sharpe=sharpe(r),
        sortino=sortino(r),
        calmar=calmar(r, trades_per_year),
    )

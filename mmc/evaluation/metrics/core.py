"""Core profitability metrics.

Formula parity with :class:`mmc.backtest.result.BacktestResult` is deliberate —
these numbers must agree with what the rest of the codebase (and the console
backtests) report, so we mirror its definitions exactly:

    win_rate      = wins / n
    profit_factor = gross_profit / gross_loss      (inf if no losses)
    expectancy    = mean(R)
    payoff_ratio  = avg_win_R / avg_loss_R
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict

import numpy as np


@dataclass
class CoreMetrics:
    n: int
    wins: int
    losses: int
    win_rate: float
    total_r: float
    expectancy: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    avg_win_r: float
    avg_loss_r: float          # positive magnitude of the average loss
    payoff_ratio: float

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)


def compute(r: np.ndarray) -> CoreMetrics:
    """Core metrics over an R-multiple array (one element per filled trade)."""
    r = np.asarray(r, dtype=float)
    n = int(r.size)
    if n == 0:
        return CoreMetrics(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    wins_mask = r > 0
    losses_mask = r < 0
    wins = int(wins_mask.sum())
    losses = int(losses_mask.sum())

    gross_profit = float(r[wins_mask].sum())
    gross_loss = float(-r[losses_mask].sum())          # positive
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (
        float("inf") if gross_profit > 0 else 0.0
    )

    avg_win_r = float(r[wins_mask].mean()) if wins else 0.0
    avg_loss_r = float(-r[losses_mask].mean()) if losses else 0.0
    payoff_ratio = (avg_win_r / avg_loss_r) if avg_loss_r > 0 else (
        float("inf") if avg_win_r > 0 else 0.0
    )

    return CoreMetrics(
        n=n,
        wins=wins,
        losses=losses,
        win_rate=wins / n,
        total_r=float(r.sum()),
        expectancy=float(r.mean()),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        avg_win_r=avg_win_r,
        avg_loss_r=avg_loss_r,
        payoff_ratio=payoff_ratio,
    )

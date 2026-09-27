"""Drawdown / risk layer — the part missing from the vanity table entirely.

Built on the cumulative-R equity curve (trade order). A -50R drawdown that
resolves in two weeks is a very different animal from one that takes eight
months, so we report depth AND duration, plus the streak length that actually
breaks traders psychologically.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Optional

import numpy as np
import pandas as pd


@dataclass
class DrawdownMetrics:
    max_dd_r: float                 # deepest peak-to-trough, in R (positive)
    max_dd_pct: float               # same, as % of the running peak equity
    dd_duration_trades: int         # longest underwater stretch, in trades
    dd_duration_days: Optional[float]  # same in calendar days (None w/o times)
    longest_losing_streak: int
    recovery_factor: float          # total R / max DD (R)
    ulcer_index: float              # RMS of % drawdown — depth AND persistence

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)


def equity_curve_r(r: np.ndarray) -> np.ndarray:
    """Cumulative R over trades (mirrors BacktestResult.equity_curve)."""
    return np.cumsum(np.asarray(r, dtype=float))


def _underwater(equity: np.ndarray):
    """Return (drawdown_r, running_peak) arrays. drawdown_r >= 0 is peak-minus-
    equity in R at each point."""
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    return dd, peak


def compute(r: np.ndarray, entry_times: Optional[pd.Series] = None) -> DrawdownMetrics:
    """Drawdown metrics for a strategy's R series (trade order).

    ``entry_times`` (optional) enables the calendar-days duration; without it
    that field is ``None``.
    """
    r = np.asarray(r, dtype=float)
    n = r.size
    if n == 0:
        return DrawdownMetrics(0.0, 0.0, 0, None, 0, 0.0, 0.0)

    equity = equity_curve_r(r)
    dd, peak = _underwater(equity)

    max_dd_r = float(dd.max())

    # Percent drawdown relative to a notional starting equity so % is meaningful
    # even on a pure-R curve: treat starting equity as max peak reached (a
    # conservative denominator) -> % = dd / (peak). Guard peak<=0 early on.
    safe_peak = np.where(peak > 0, peak, np.nan)
    dd_pct_series = np.where(np.isfinite(safe_peak), dd / safe_peak, 0.0)
    max_dd_pct = float(np.nanmax(dd_pct_series)) if np.isfinite(dd_pct_series).any() else 0.0

    # Longest underwater stretch (in trades): consecutive run where dd > 0.
    dur_trades = _longest_underwater_run(dd)

    # Calendar days of the worst underwater stretch.
    dur_days = None
    if entry_times is not None and len(entry_times) == n:
        dur_days = _worst_underwater_days(dd, pd.to_datetime(pd.Series(entry_times).values))

    longest_streak = _longest_losing_streak(r)

    total_r = float(r.sum())
    recovery = (total_r / max_dd_r) if max_dd_r > 0 else (
        float("inf") if total_r > 0 else 0.0
    )

    ulcer = float(np.sqrt(np.mean(np.square(dd_pct_series * 100.0))))

    return DrawdownMetrics(
        max_dd_r=max_dd_r,
        max_dd_pct=max_dd_pct,
        dd_duration_trades=dur_trades,
        dd_duration_days=dur_days,
        longest_losing_streak=longest_streak,
        recovery_factor=recovery,
        ulcer_index=ulcer,
    )


def _longest_losing_streak(r: np.ndarray) -> int:
    streak = worst = 0
    for x in r:
        if x < 0:
            streak += 1
            worst = max(worst, streak)
        else:
            streak = 0
    return worst


def _longest_underwater_run(dd: np.ndarray) -> int:
    run = worst = 0
    for x in dd:
        if x > 1e-12:
            run += 1
            worst = max(worst, run)
        else:
            run = 0
    return worst


def _worst_underwater_days(dd: np.ndarray, times: np.ndarray) -> float:
    """Calendar span (days) of the single longest underwater stretch."""
    best = 0.0
    start = None
    for i, x in enumerate(dd):
        if x > 1e-12:
            if start is None:
                start = i
        else:
            if start is not None:
                span = (times[i] - times[start]) / np.timedelta64(1, "D")
                best = max(best, float(span))
                start = None
    if start is not None:  # still underwater at the end
        span = (times[-1] - times[start]) / np.timedelta64(1, "D")
        best = max(best, float(span))
    return best

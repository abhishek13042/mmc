"""Portfolio layer — critical because the 15 strategies run TOGETHER on one
account, so their tail risks add up rather than diversifying away.

  * correlation matrix of daily R across strategies — same symbol / overlapping
    timeframes means correlated drawdowns, not real diversification.
  * combined equity on the true interleaved trade timeline, sized exactly like
    the live fleet (per-strategy dynamic risk: halve after that strategy's own
    loss, reset on its win, floor 1/16). Parity with
    ``examples/mt5_oos_test.py::compounded_equity`` — reimplemented here so the
    module never imports the MetaTrader5-dependent example script.
  * peak concurrent open-risk — how much capital is live at the worst moment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

BASE_RISK_PCT = 0.5
RISK_FLOOR = BASE_RISK_PCT / 16.0


@dataclass
class PortfolioMetrics:
    n_strategies: int
    combined_total_r: float
    combined_final_balance: float
    combined_max_dd_pct: float
    combined_max_dd_r: float
    mean_pairwise_corr: float
    max_pairwise_corr: float
    peak_concurrent_positions: int
    corr_matrix: Optional[pd.DataFrame] = None
    equity_curve: Optional[pd.DataFrame] = None    # [time, balance]
    equity_curve_r: Optional[pd.DataFrame] = None  # [time, cum_r]

    def as_dict(self) -> Dict[str, float]:
        return {
            "n_strategies": self.n_strategies,
            "combined_total_r": self.combined_total_r,
            "combined_final_balance": self.combined_final_balance,
            "combined_max_dd_pct": self.combined_max_dd_pct,
            "combined_max_dd_r": self.combined_max_dd_r,
            "mean_pairwise_corr": self.mean_pairwise_corr,
            "max_pairwise_corr": self.max_pairwise_corr,
            "peak_concurrent_positions": self.peak_concurrent_positions,
        }


def correlation_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Pairwise correlation of DAILY summed R per strategy (aligned by date)."""
    s = df[["strategy_id", "entry_time", "r_multiple"]].copy()
    s["date"] = pd.to_datetime(s["entry_time"]).dt.date
    daily = s.pivot_table(index="date", columns="strategy_id",
                          values="r_multiple", aggfunc="sum")
    # Days a strategy didn't trade contribute 0 R (flat), not NaN.
    daily = daily.fillna(0.0)
    if daily.shape[1] < 2:
        return pd.DataFrame()
    return daily.corr()


def _offdiag(m: pd.DataFrame) -> np.ndarray:
    if m.empty:
        return np.array([])
    a = m.to_numpy(dtype=float)
    mask = ~np.eye(a.shape[0], dtype=bool)
    vals = a[mask]
    return vals[np.isfinite(vals)]


def compounded_equity(
    df: pd.DataFrame, start_balance: float = 10_000.0
) -> Tuple[float, pd.DataFrame]:
    """True-timeline compounded balance across all strategies (fleet sizing).

    Faithful reimplementation of the example script: each strategy keeps its own
    risk multiplier, halved after its loss and reset to 1.0 after its win,
    floored at 1/16.
    """
    t = df.sort_values("entry_time").reset_index(drop=True)
    balance = start_balance
    risk_mult = {s: 1.0 for s in t["strategy_id"].unique()}
    rows = []
    for _, row in t.iterrows():
        strat = row["strategy_id"]
        risk_pct = BASE_RISK_PCT * risk_mult[strat]
        risk_cash = balance * (risk_pct / 100.0)
        balance += risk_cash * float(row["r_multiple"])
        if bool(row.get("win", row["r_multiple"] > 0)):
            risk_mult[strat] = 1.0
        else:
            risk_mult[strat] = max(RISK_FLOOR / BASE_RISK_PCT, risk_mult[strat] * 0.5)
        rows.append({"time": row["entry_time"], "balance": balance})
    return balance, pd.DataFrame(rows)


def peak_concurrent_positions(df: pd.DataFrame) -> int:
    """Max number of simultaneously-open positions across the fleet.

    Uses entry/exit times when available (a sweep line over open/close events);
    falls back to same-day co-occurrence when exit_time is missing.
    """
    if "exit_time" in df.columns and df["exit_time"].notna().any():
        events: List[Tuple[pd.Timestamp, int]] = []
        for _, r in df.iterrows():
            et = pd.to_datetime(r["entry_time"])
            xt = pd.to_datetime(r["exit_time"]) if pd.notna(r.get("exit_time")) else et
            events.append((et, +1))
            events.append((xt, -1))
        events.sort(key=lambda e: (e[0], e[1]))  # closes (-1) before opens at a tie
        cur = peak = 0
        for _, delta in events:
            cur += delta
            peak = max(peak, cur)
        return int(peak)
    # fallback: max positions opened on the same calendar day
    d = pd.to_datetime(df["entry_time"]).dt.date
    return int(d.value_counts().max()) if len(d) else 0


def compute(df: pd.DataFrame, start_balance: float = 10_000.0) -> PortfolioMetrics:
    """Portfolio-level metrics over a multi-strategy trade log."""
    n_strats = df["strategy_id"].nunique()

    corr = correlation_matrix(df)
    off = _offdiag(corr)
    mean_c = float(np.mean(off)) if off.size else 0.0
    max_c = float(np.max(off)) if off.size else 0.0

    final_bal, eq = compounded_equity(df, start_balance)
    if not eq.empty:
        peak = eq["balance"].cummax()
        dd_pct = float(((eq["balance"] - peak) / peak).min())  # negative
    else:
        dd_pct = 0.0

    # combined R curve (simple interleaved sum of R, true time order)
    t = df.sort_values("entry_time")
    cum_r = t["r_multiple"].cumsum().to_numpy()
    eq_r = pd.DataFrame({"time": t["entry_time"].to_numpy(), "cum_r": cum_r})
    max_dd_r = 0.0
    if cum_r.size:
        peak_r = np.maximum.accumulate(cum_r)
        max_dd_r = float((peak_r - cum_r).max())

    return PortfolioMetrics(
        n_strategies=int(n_strats),
        combined_total_r=float(df["r_multiple"].sum()),
        combined_final_balance=float(final_bal),
        combined_max_dd_pct=abs(dd_pct) * 100.0,
        combined_max_dd_r=max_dd_r,
        mean_pairwise_corr=mean_c,
        max_pairwise_corr=max_c,
        peak_concurrent_positions=peak_concurrent_positions(df),
        corr_matrix=corr if not corr.empty else None,
        equity_curve=eq if not eq.empty else None,
        equity_curve_r=eq_r,
    )

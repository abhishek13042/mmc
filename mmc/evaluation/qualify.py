"""Per-strategy qualification: run every metric family, then apply the
pre-committed pass/fail thresholds from :class:`QualifyConfig`.

Tiers:
  * INSUFFICIENT_DATA — N < min_n. The gate the whole checklist hangs on: below
    this everything else is noise, so we report the numbers but don't bless it.
  * PASS  — cleared every gate.
  * FAIL  — enough data, but missed one or more gates (reasons listed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from mmc.evaluation.config import QualifyConfig
from mmc.evaluation.metrics import (
    core as m_core,
    statval as m_stat,
    drawdown as m_dd,
    riskadj as m_ra,
    stability as m_stab,
    robustness as m_rob,
)


class Tier(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class Qualification:
    tier: Tier
    reasons: List[str] = field(default_factory=list)   # why it failed / is thin
    checks: Dict[str, bool] = field(default_factory=dict)


@dataclass
class StrategyReport:
    strategy_id: str
    core: m_core.CoreMetrics
    wilson_low: float
    wilson_high: float
    pf_band: m_stat.BootstrapBand
    exp_band: m_stat.BootstrapBand
    exp_stderr: float
    drawdown: m_dd.DrawdownMetrics
    riskadj: m_ra.RiskAdjMetrics
    stability: m_stab.StabilityMetrics
    isoos: m_rob.ISOOSDecay
    montecarlo: m_rob.MonteCarlo
    qualification: Qualification

    # execution-reality sensitivity (spread stress + commission drag)
    stressed_pf: float = 0.0
    stressed_exp_r: float = 0.0

    def flat_row(self) -> Dict[str, object]:
        """One flat dict per strategy for the summary CSV/Markdown table."""
        c, d, ra, st, io, mc = (
            self.core, self.drawdown, self.riskadj,
            self.stability, self.isoos, self.montecarlo,
        )
        return {
            "strategy_id": self.strategy_id,
            "tier": self.qualification.tier.value,
            "verdict": "; ".join(self.qualification.reasons) or "clears all gates",
            "N": c.n,
            "win_rate": c.win_rate,
            "wr_ci_low": self.wilson_low,
            "wr_ci_high": self.wilson_high,
            "profit_factor": c.profit_factor,
            "pf_boot_p5": self.pf_band.p5,
            "pf_boot_low": self.pf_band.low,
            "pf_boot_high": self.pf_band.high,
            "exp_r": c.expectancy,
            "exp_r_stderr": self.exp_stderr,
            "total_r": c.total_r,
            "payoff_ratio": c.payoff_ratio,
            "max_dd_r": d.max_dd_r,
            "max_dd_pct": d.max_dd_pct,
            "dd_dur_trades": d.dd_duration_trades,
            "dd_dur_days": d.dd_duration_days,
            "longest_losing_streak": d.longest_losing_streak,
            "recovery_factor": d.recovery_factor,
            "ulcer_index": d.ulcer_index,
            "sortino": ra.sortino,
            "calmar": ra.calmar,
            "sharpe": ra.sharpe,
            "skew": st.skew,
            "kurtosis": st.kurtosis,
            "return_concentration": st.concentration,
            "is_pf": io.is_pf,
            "oos_pf": io.oos_pf,
            "is_oos_pf_decay": io.pf_decay,
            "mc_dd_p95_r": mc.dd_p95,
            "mc_prob_worse_dd": mc.prob_worse_than_observed,
            "stressed_pf": self.stressed_pf,
            "stressed_exp_r": self.stressed_exp_r,
        }


def _stressed(r: np.ndarray, cfg: QualifyConfig, spread_r_per_trade: np.ndarray):
    """Re-price PF/ExpR after inflating spread by ``spread_stress`` and adding a
    flat ``commission_r`` drag. ``spread_r_per_trade`` is the spread already
    charged (in R) per trade, if the log carries it; else assume 0 extra."""
    extra = (cfg.spread_stress - 1.0) * spread_r_per_trade + cfg.commission_r
    stressed = r - extra
    c = m_core.compute(stressed)
    return c.profit_factor, c.expectancy


def evaluate_strategy(
    strategy_id: str,
    trades: pd.DataFrame,
    cfg: QualifyConfig,
    is_table: Optional[pd.DataFrame] = None,
) -> StrategyReport:
    """Run every metric family for one strategy and qualify it."""
    r = trades["r_multiple"].to_numpy(dtype=float)
    times = trades["entry_time"] if "entry_time" in trades.columns else None

    core = m_core.compute(r)
    wl, wh = m_stat.wilson_interval(core.wins, core.n, cfg.conf_level)
    pf_band, exp_band = m_stat.bootstrap_bands(
        r, cfg.bootstrap_iters, cfg.conf_level, cfg.rng_seed)
    exp_se = m_stat.expectancy_stderr(r)
    dd = m_dd.compute(r, times)
    ra = m_ra.compute(r, cfg.trades_per_year)
    stab = m_stab.compute(r, times)
    isoos = m_rob.is_oos_decay(strategy_id, r, is_table)
    mc = m_rob.monte_carlo(r, cfg.mc_iters, cfg.rng_seed)

    # spread_cost is recorded by the exporter in R units (spread / risk), i.e.
    # the R already deducted from each trade's gross. Absent -> no extra drag.
    spread_r = (np.abs(trades["spread_cost"].to_numpy(dtype=float))
                if "spread_cost" in trades.columns else np.zeros_like(r))
    spread_r = np.nan_to_num(spread_r)
    stressed_pf, stressed_exp = _stressed(r, cfg, spread_r)

    qual = qualify_strategy(core, pf_band, dd, isoos, cfg)

    return StrategyReport(
        strategy_id=strategy_id,
        core=core, wilson_low=wl, wilson_high=wh,
        pf_band=pf_band, exp_band=exp_band, exp_stderr=exp_se,
        drawdown=dd, riskadj=ra, stability=stab, isoos=isoos, montecarlo=mc,
        qualification=qual, stressed_pf=stressed_pf, stressed_exp_r=stressed_exp,
    )


def qualify_strategy(
    core: m_core.CoreMetrics,
    pf_band: m_stat.BootstrapBand,
    dd: m_dd.DrawdownMetrics,
    isoos: m_rob.ISOOSDecay,
    cfg: QualifyConfig,
) -> Qualification:
    """Apply the four pre-committed gates and return the tier + reasons."""
    # Gate 0: sample size.
    if core.n < cfg.min_n:
        return Qualification(
            tier=Tier.INSUFFICIENT_DATA,
            reasons=[f"N={core.n} < min_n={cfg.min_n}"],
            checks={"sample_size": False},
        )

    checks: Dict[str, bool] = {"sample_size": True}
    reasons: List[str] = []

    # Gate 1: pessimistic (5th-pct bootstrap) PF, not the point estimate.
    ok_pf = pf_band.p5 > cfg.min_bootstrap_pf
    checks["bootstrap_pf"] = ok_pf
    if not ok_pf:
        reasons.append(
            f"bootstrap PF p5={pf_band.p5:.2f} <= {cfg.min_bootstrap_pf}")

    # Gate 2: recovery factor.
    ok_rec = dd.recovery_factor > cfg.min_recovery
    checks["recovery_factor"] = ok_rec
    if not ok_rec:
        reasons.append(
            f"recovery factor={dd.recovery_factor:.2f} <= {cfg.min_recovery}")

    # Gate 3: IS/OOS PF decay (only if we have an in-sample baseline).
    if isoos.pf_decay is None:
        checks["is_oos_decay"] = True   # cannot fail what we can't measure
        reasons.append("no in-sample baseline (IS/OOS decay not checked)")
    else:
        ok_decay = isoos.pf_decay < cfg.max_is_oos_decay
        checks["is_oos_decay"] = ok_decay
        if not ok_decay:
            reasons.append(
                f"IS/OOS PF decay={isoos.pf_decay:+.0%} >= {cfg.max_is_oos_decay:.0%}")

    passed = all(v for k, v in checks.items())
    tier = Tier.PASS if passed else Tier.FAIL
    if passed and not reasons:
        reasons = []
    return Qualification(tier=tier, reasons=reasons, checks=checks)

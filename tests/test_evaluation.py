"""Tests for the strategy evaluation pipeline (mmc.evaluation).

The metrics are validated against hand-computed values on deterministic
R-multiple sequences; stochastic pieces (bootstrap / Monte Carlo) are checked
for structural sanity with a fixed seed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mmc.evaluation.schema import normalise_trades, SchemaError
from mmc.evaluation.config import QualifyConfig
from mmc.evaluation.metrics import core, statval, drawdown, riskadj, stability, portfolio
from mmc.evaluation.metrics import robustness
from mmc.evaluation.qualify import evaluate_strategy, Tier


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _trades(r, strategy_id="TEST_H4_H1_rr4", start="2024-01-01", freq="D"):
    """Build a normalised trade DataFrame from an R array."""
    r = np.asarray(r, dtype=float)
    t = pd.date_range(start, periods=len(r), freq=freq)
    df = pd.DataFrame({
        "strategy_id": strategy_id,
        "entry_time": t,
        "exit_time": t + pd.Timedelta(hours=1),
        "r_multiple": r,
        "outcome": np.where(r > 0, "win", "loss"),
        "spread_cost": 0.02,
    })
    return normalise_trades(df)


# repeating [+4, -1] pattern, 100 cycles -> 200 trades, WR 50%, PF 4
PATTERN = np.tile([4.0, -1.0], 100)


# --------------------------------------------------------------------------- #
# schema
# --------------------------------------------------------------------------- #

def test_schema_requires_core_columns():
    with pytest.raises(SchemaError):
        normalise_trades(pd.DataFrame({"foo": [1]}))


def test_schema_parses_strategy_id_and_win():
    df = normalise_trades(pd.DataFrame({
        "strategy_id": ["EURUSD_H4_H1_rr4"],
        "entry_time": ["2024-01-01"],
        "r_multiple": [4.0],
    }))
    assert df.loc[0, "pair"] == "EURUSD"
    assert df.loc[0, "combo"] == "H4_H1"
    assert df.loc[0, "rr"] == 4.0
    assert bool(df.loc[0, "win"]) is True


# --------------------------------------------------------------------------- #
# core metrics
# --------------------------------------------------------------------------- #

def test_core_metrics_exact():
    c = core.compute(PATTERN)
    assert c.n == 200
    assert c.wins == 100 and c.losses == 100
    assert c.win_rate == pytest.approx(0.5)
    assert c.total_r == pytest.approx(300.0)
    assert c.expectancy == pytest.approx(1.5)
    assert c.gross_profit == pytest.approx(400.0)
    assert c.gross_loss == pytest.approx(100.0)
    assert c.profit_factor == pytest.approx(4.0)
    assert c.avg_win_r == pytest.approx(4.0)
    assert c.avg_loss_r == pytest.approx(1.0)
    assert c.payoff_ratio == pytest.approx(4.0)


def test_profit_factor_infinite_when_no_losses():
    c = core.compute(np.array([1.0, 2.0, 3.0]))
    assert c.profit_factor == float("inf")


# --------------------------------------------------------------------------- #
# statistical validity
# --------------------------------------------------------------------------- #

def test_wilson_interval_brackets_point_estimate():
    lo, hi = statval.wilson_interval(50, 200, 0.95)
    assert 0.0 < lo < 0.25 < hi < 0.5
    # known value for p=.25,n=200: ~[0.196, 0.312]
    assert lo == pytest.approx(0.196, abs=0.01)
    assert hi == pytest.approx(0.313, abs=0.01)


def test_bootstrap_band_brackets_and_reproducible():
    pf_band, exp_band = statval.bootstrap_bands(PATTERN, iters=500, seed=7)
    assert pf_band.point == pytest.approx(4.0)
    assert pf_band.low <= pf_band.point <= pf_band.high
    assert exp_band.low <= exp_band.point <= exp_band.high
    # determinism
    pf2, _ = statval.bootstrap_bands(PATTERN, iters=500, seed=7)
    assert pf_band.p5 == pytest.approx(pf2.p5)


# --------------------------------------------------------------------------- #
# drawdown
# --------------------------------------------------------------------------- #

def test_drawdown_and_streak_exact():
    # win then three losses, repeated: dd within cycle is 3R, streak 3
    r = np.tile([4.0, -1.0, -1.0, -1.0], 50)   # 200 trades
    d = drawdown.compute(r, pd.Series(pd.date_range("2024-01-01", periods=200)))
    assert d.longest_losing_streak == 3
    assert d.max_dd_r == pytest.approx(3.0)
    assert d.recovery_factor == pytest.approx(50.0 / 3.0)  # total 50R / 3R
    assert d.dd_duration_trades == 3


def test_recovery_factor_infinite_without_drawdown():
    d = drawdown.compute(np.array([1.0, 1.0, 1.0]))
    assert d.max_dd_r == pytest.approx(0.0)
    assert d.recovery_factor == float("inf")


# --------------------------------------------------------------------------- #
# risk-adjusted
# --------------------------------------------------------------------------- #

def test_sortino_and_calmar_exact():
    # WR 25% pattern [4,-1,-1,-1]: mean=0.25, downside dev=sqrt(0.75)
    r = np.tile([4.0, -1.0, -1.0, -1.0], 50)
    s = riskadj.sortino(r)
    assert s == pytest.approx(0.25 / np.sqrt(0.75), rel=1e-6)
    c = riskadj.calmar(r, trades_per_year=252.0)
    assert c == pytest.approx(0.25 * 252.0 / 3.0, rel=1e-6)


def test_sortino_infinite_without_downside():
    assert riskadj.sortino(np.array([1.0, 2.0])) == float("inf")


# --------------------------------------------------------------------------- #
# stability
# --------------------------------------------------------------------------- #

def test_skew_positive_for_asymmetric_wins():
    r = np.tile([4.0, -1.0, -1.0, -1.0], 50)
    st = stability.compute(r, pd.Series(pd.date_range("2024-01-01", periods=200)))
    assert st.skew > 0                      # few big wins, many small losses
    assert len(st.buckets) >= 1


# --------------------------------------------------------------------------- #
# robustness
# --------------------------------------------------------------------------- #

def test_monte_carlo_structure():
    r = np.tile([4.0, -1.0, -1.0, -1.0], 50)
    mc = robustness.monte_carlo(r, iters=300, seed=3)
    assert mc.n_iters == 300
    assert mc.dd_p95 >= mc.dd_median >= 0
    assert 0.0 <= mc.prob_worse_than_observed <= 1.0
    # permutation keeps the trade set -> terminal equity constant across shuffles
    assert mc.final_r_median == pytest.approx(r.sum())


def test_is_oos_decay_without_baseline_is_none():
    r = PATTERN
    d = robustness.is_oos_decay("NOPE_X_Y_rr4", r, table=None)
    assert d.pf_decay is None
    assert d.oos_pf == pytest.approx(4.0)


# --------------------------------------------------------------------------- #
# qualification end-to-end
# --------------------------------------------------------------------------- #

def test_qualify_pass_strong_strategy():
    cfg = QualifyConfig()
    rep = evaluate_strategy("STRONG_H4_H1_rr4", _trades(PATTERN), cfg, is_table=None)
    assert rep.qualification.tier == Tier.PASS


def test_qualify_insufficient_data():
    cfg = QualifyConfig()
    rep = evaluate_strategy("THIN_H4_H1_rr4", _trades(PATTERN[:20]), cfg, is_table=None)
    assert rep.qualification.tier == Tier.INSUFFICIENT_DATA


def test_qualify_fail_weak_strategy():
    cfg = QualifyConfig()
    # PF 0.5, negative expectancy -> fails PF & recovery gates
    r = np.tile([1.0, -1.0, -1.0], 70)      # 210 trades
    rep = evaluate_strategy("WEAK_H4_H1_rr4", _trades(r), cfg, is_table=None)
    assert rep.qualification.tier == Tier.FAIL
    assert rep.qualification.checks["bootstrap_pf"] is False


# --------------------------------------------------------------------------- #
# portfolio
# --------------------------------------------------------------------------- #

def test_portfolio_runs_over_two_strategies():
    a = _trades(PATTERN, strategy_id="A_H4_H1_rr4")
    b = _trades(np.tile([2.0, -1.0], 100), strategy_id="B_H4_H1_rr4")
    df = pd.concat([a, b], ignore_index=True)
    p = portfolio.compute(df)
    assert p.n_strategies == 2
    assert p.corr_matrix is not None and p.corr_matrix.shape == (2, 2)
    assert p.combined_final_balance > 0
    assert p.peak_concurrent_positions >= 1

"""Report writer — turns per-strategy :class:`StrategyReport` objects and the
portfolio metrics into CSV + Markdown + PNG artifacts under a timestamped
``reports/<run_ts>/`` folder.

Charts use a headless matplotlib backend so this runs on a server with no
display. seaborn is used for the correlation heatmap when available.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

try:
    import seaborn as sns
    _HAVE_SNS = True
except Exception:  # pragma: no cover
    _HAVE_SNS = False

from mmc.evaluation.config import QualifyConfig
from mmc.evaluation.qualify import StrategyReport
from mmc.evaluation.metrics import portfolio as m_port


# --------------------------------------------------------------------------- #
# Summary table
# --------------------------------------------------------------------------- #

# Columns shown (in order) in the human-facing Markdown table; the CSV keeps all.
_MD_COLS = [
    ("strategy_id", "Strategy", "{}"),
    ("tier", "Tier", "{}"),
    ("N", "N", "{:d}"),
    ("win_rate", "WR", "{:.1%}"),
    ("wr_ci_low", "WR CI-", "{:.1%}"),
    ("wr_ci_high", "WR CI+", "{:.1%}"),
    ("profit_factor", "PF", "{:.2f}"),
    ("pf_boot_p5", "PF p5", "{:.2f}"),
    ("exp_r", "ExpR", "{:+.3f}"),
    ("total_r", "TotR", "{:+.1f}"),
    ("max_dd_r", "MaxDD(R)", "{:.1f}"),
    ("max_dd_pct", "MaxDD%", "{:.1f}"),
    ("longest_losing_streak", "MaxLoseStreak", "{:d}"),
    ("recovery_factor", "Recovery", "{:.2f}"),
    ("ulcer_index", "Ulcer", "{:.2f}"),
    ("sortino", "Sortino", "{:.2f}"),
    ("calmar", "Calmar", "{:.2f}"),
    ("skew", "Skew", "{:+.2f}"),
    ("is_oos_pf_decay", "IS/OOS decay", "{:+.0%}"),
    ("verdict", "Verdict", "{}"),
]


def _fmt(val, spec: str) -> str:
    if val is None or (isinstance(val, float) and not np.isfinite(val)):
        return "—" if val is None else ("inf" if val == float("inf") else "—")
    try:
        return spec.format(val)
    except (ValueError, TypeError):
        return str(val)


def build_summary_frame(reports: List[StrategyReport]) -> pd.DataFrame:
    return pd.DataFrame([r.flat_row() for r in reports])


def summary_markdown(df: pd.DataFrame, cfg: QualifyConfig,
                     portfolio: Optional[m_port.PortfolioMetrics]) -> str:
    lines: List[str] = []
    lines.append("# Strategy Evaluation Summary\n")
    lines.append(f"_Generated {datetime.now():%Y-%m-%d %H:%M:%S}_\n")
    lines.append(f"Strategies evaluated: **{len(df)}**  |  "
                 f"Gates: N≥{cfg.min_n}, bootstrap-PF-p5>{cfg.min_bootstrap_pf}, "
                 f"recovery>{cfg.min_recovery}, IS/OOS decay<{cfg.max_is_oos_decay:.0%}\n")

    counts = df["tier"].value_counts().to_dict()
    lines.append("**Tier counts:** " + ", ".join(
        f"{k}={v}" for k, v in counts.items()) + "\n")

    # header
    header = "| " + " | ".join(h for _, h, _ in _MD_COLS) + " |"
    sep = "| " + " | ".join("---" for _ in _MD_COLS) + " |"
    lines.append(header)
    lines.append(sep)
    # sort: PASS first, then FAIL, then INSUFFICIENT; within tier by ExpR desc
    order = {"PASS": 0, "FAIL": 1, "INSUFFICIENT_DATA": 2}
    df_sorted = df.assign(_o=df["tier"].map(order).fillna(3)).sort_values(
        ["_o", "exp_r"], ascending=[True, False])
    for _, row in df_sorted.iterrows():
        cells = [_fmt(row.get(k), spec) for k, _, spec in _MD_COLS]
        lines.append("| " + " | ".join(cells) + " |")

    if portfolio is not None:
        lines.append("\n## Portfolio (all strategies on one account)\n")
        p = portfolio
        lines.append(f"- Combined total R: **{p.combined_total_r:+.1f}R**")
        lines.append(f"- Compounded final balance (from $10k, fleet sizing): "
                     f"**${p.combined_final_balance:,.0f}**")
        lines.append(f"- Combined max drawdown: **{p.combined_max_dd_pct:.1f}%** "
                     f"/ **{p.combined_max_dd_r:.1f}R**")
        lines.append(f"- Mean / max pairwise correlation: "
                     f"**{p.mean_pairwise_corr:+.2f}** / **{p.max_pairwise_corr:+.2f}**")
        lines.append(f"- Peak concurrent open positions: "
                     f"**{p.peak_concurrent_positions}**")
        lines.append("\n> Correlated strategies mean the portfolio drawdown is "
                     "worse than summing individual max-DDs. Watch the max "
                     "pairwise correlation.\n")

    lines.append("\n## Caveats\n")
    lines.append("- Fills are idealised (exact SL/TP, no requotes/slippage); the "
                 "spread charged is a fixed per-trade assumption (default "
                 "0.20 pips), not the true time-varying spread. See the "
                 "`stressed_pf`/`stressed_exp_r` columns in `summary.csv` for a "
                 "1.5× spread + commission sensitivity.")
    lines.append("- IS/OOS decay compares this log against the training-time "
                 "in-sample numbers in `RESULTS_TABLE.csv`; strategies without a "
                 "matching row are not decay-checked.")
    return "\n".join(lines) + "\n"


def qualification_markdown(reports: List[StrategyReport], cfg: QualifyConfig) -> str:
    lines = ["# Qualification Verdicts\n"]
    lines.append("Pre-committed gates (decided before seeing the numbers):\n")
    lines.append(f"1. **N ≥ {cfg.min_n}** — else INSUFFICIENT_DATA.")
    lines.append(f"2. **bootstrap PF (5th pct) > {cfg.min_bootstrap_pf}** — "
                 "pessimistic, not point estimate.")
    lines.append(f"3. **recovery factor > {cfg.min_recovery}**.")
    lines.append(f"4. **IS/OOS PF decay < {cfg.max_is_oos_decay:.0%}**.\n")
    for r in sorted(reports, key=lambda x: x.qualification.tier.value):
        q = r.qualification
        checks = "  ".join(f"{k}={'✓' if v else '✗'}" for k, v in q.checks.items())
        reason = ("; ".join(q.reasons)) if q.reasons else "clears all gates"
        lines.append(f"- **{r.strategy_id}** → **{q.tier.value}**  ({checks})  "
                     f"— {reason}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #

def _plot_correlation(corr: pd.DataFrame, path: str) -> None:
    fig, ax = plt.subplots(figsize=(max(6, 0.6 * len(corr)), max(5, 0.5 * len(corr))))
    if _HAVE_SNS:
        sns.heatmap(corr, annot=len(corr) <= 16, fmt=".2f", cmap="RdBu_r",
                    center=0, vmin=-1, vmax=1, ax=ax, cbar_kws={"label": "corr"})
    else:  # pragma: no cover
        im = ax.imshow(corr.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1)
        ax.set_xticks(range(len(corr))); ax.set_xticklabels(corr.columns, rotation=90)
        ax.set_yticks(range(len(corr))); ax.set_yticklabels(corr.index)
        fig.colorbar(im, ax=ax, label="corr")
    ax.set_title("Cross-strategy daily-R correlation")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_portfolio_equity(p: m_port.PortfolioMetrics, path: str) -> None:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 1]})
    eq = p.equity_curve
    ax1.plot(pd.to_datetime(eq["time"]), eq["balance"], color="#1f77b4", lw=1.4)
    ax1.set_ylabel("Balance ($)")
    ax1.set_title(f"Fleet compounded equity  (final ${p.combined_final_balance:,.0f}, "
                  f"max DD {p.combined_max_dd_pct:.1f}%)")
    ax1.grid(alpha=0.3)
    peak = eq["balance"].cummax()
    dd = (eq["balance"] - peak) / peak * 100.0
    ax2.fill_between(pd.to_datetime(eq["time"]), dd, 0, color="#d62728", alpha=0.5)
    ax2.set_ylabel("Drawdown %")
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _plot_montecarlo(report: StrategyReport, path: str) -> None:
    mc = report.montecarlo
    if mc.curves is None or len(mc.curves) == 0:
        return
    fig, ax = plt.subplots(figsize=(9, 5))
    for curve in mc.curves:
        ax.plot(curve, color="#888888", alpha=0.15, lw=0.7)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_title(f"{report.strategy_id}  Monte Carlo trade-order shuffle "
                 f"({mc.n_iters} runs)\nobserved max DD={mc.observed_max_dd_r:.1f}R, "
                 f"P(worse)={mc.prob_worse_than_observed:.0%}, "
                 f"DD p95={mc.dd_p95:.1f}R")
    ax.set_xlabel("Trade #"); ax.set_ylabel("Cumulative R")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def write_report(
    reports: List[StrategyReport],
    portfolio: Optional[m_port.PortfolioMetrics],
    out_dir: str,
    cfg: QualifyConfig,
) -> str:
    """Write CSV + Markdown + PNGs into ``out_dir/<run_ts>/`` and return the path."""
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(out_dir, run_ts)
    os.makedirs(dest, exist_ok=True)

    df = build_summary_frame(reports)
    df.to_csv(os.path.join(dest, "summary.csv"), index=False)

    with open(os.path.join(dest, "summary.md"), "w", encoding="utf-8") as f:
        f.write(summary_markdown(df, cfg, portfolio))
    with open(os.path.join(dest, "qualification.md"), "w", encoding="utf-8") as f:
        f.write(qualification_markdown(reports, cfg))

    if portfolio is not None:
        if portfolio.corr_matrix is not None and len(portfolio.corr_matrix) >= 2:
            _plot_correlation(portfolio.corr_matrix,
                              os.path.join(dest, "portfolio_correlation.png"))
        if portfolio.equity_curve is not None and not portfolio.equity_curve.empty:
            _plot_portfolio_equity(portfolio,
                                   os.path.join(dest, "portfolio_equity.png"))

    # Monte Carlo fan per qualifying strategy (skip thin ones to save files).
    for rep in reports:
        if rep.core.n >= cfg.min_n:
            _plot_montecarlo(rep, os.path.join(dest, f"mc_{rep.strategy_id}.png"))

    return dest

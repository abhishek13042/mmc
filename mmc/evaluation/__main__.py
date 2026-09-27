"""CLI: evaluate a per-trade log and write the full report bundle.

    python -m mmc.evaluation --trades mmc/evaluation/data/trades_master.csv
    python -m mmc.evaluation --trades <csv> --out mmc/evaluation/reports \
                             --min-n 100 --bootstrap-pf 1.2 --recovery 2.0

Reads the canonical trade CSV (see mmc.evaluation.schema), runs every metric
family per strategy plus the portfolio layer, applies the pre-committed
qualification gates, and writes CSV + Markdown + PNG under reports/<run_ts>/.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

from mmc.evaluation.config import QualifyConfig
from mmc.evaluation.schema import load_trades, split_by_strategy
from mmc.evaluation.qualify import evaluate_strategy
from mmc.evaluation.metrics import portfolio as m_port
from mmc.evaluation.metrics import robustness as m_rob
from mmc.evaluation import report as m_report
from mmc.evaluation.progress import Status, Tee

_HERE = os.path.dirname(__file__)
_DEFAULT_OUT = os.path.join(_HERE, "reports")


def _build_config(args) -> QualifyConfig:
    return QualifyConfig(
        min_n=args.min_n,
        min_bootstrap_pf=args.bootstrap_pf,
        min_recovery=args.recovery,
        max_is_oos_decay=args.max_decay,
        bootstrap_iters=args.bootstrap_iters,
        mc_iters=args.mc_iters,
        rng_seed=args.seed,
        spread_stress=args.spread_stress,
        commission_r=args.commission_r,
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mmc.evaluation",
                                 description="Strategy qualification pipeline")
    ap.add_argument("--trades", required=True, help="path to the trade-log CSV")
    ap.add_argument("--out", default=_DEFAULT_OUT, help="reports base directory")
    ap.add_argument("--results-table", default=m_rob.DEFAULT_RESULTS_TABLE,
                    help="in-sample baseline CSV for IS/OOS decay")
    # gates
    ap.add_argument("--min-n", type=int, default=100)
    ap.add_argument("--bootstrap-pf", type=float, default=1.2)
    ap.add_argument("--recovery", type=float, default=2.0)
    ap.add_argument("--max-decay", type=float, default=0.30)
    # knobs
    ap.add_argument("--bootstrap-iters", type=int, default=1000)
    ap.add_argument("--mc-iters", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--spread-stress", type=float, default=1.5)
    ap.add_argument("--commission-r", type=float, default=0.0)
    args = ap.parse_args(argv)

    if not os.path.exists(args.trades):
        print(f"error: trades file not found: {args.trades}", file=sys.stderr)
        return 2

    cfg = _build_config(args)
    df = load_trades(args.trades)
    if df.empty:
        print("error: trade log is empty", file=sys.stderr)
        return 2

    is_table = m_rob.load_results_table(args.results_table)
    if is_table is None:
        print(f"note: no in-sample baseline at {args.results_table} — "
              "IS/OOS decay will be skipped.")

    by_strat = split_by_strategy(df)
    os.makedirs(args.out, exist_ok=True)
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    with Tee(os.path.join(args.out, f"eval_run_{run_ts}.log")):
        status = Status()
        status.step(f"evaluating {len(by_strat)} strategies over {len(df)} trades "
                    f"(bootstrap x{cfg.bootstrap_iters}, MC x{cfg.mc_iters}) ...")

        reports, lines = [], []
        items = list(by_strat.items())
        for k, (sid, trades) in enumerate(items, 1):
            status.bar(k - 1, len(items), f"eval {sid}")
            rep = evaluate_strategy(sid, trades, cfg, is_table)
            reports.append(rep)
            q = rep.qualification
            lines.append(f"  {sid:<24} N={rep.core.n:<5} tier={q.tier.value:<17} "
                         f"PF={rep.core.profit_factor:.2f} "
                         f"ExpR={rep.core.expectancy:+.3f} "
                         f"maxDD={rep.drawdown.max_dd_r:.1f}R")
        status.bar(len(items), len(items), "evaluated")
        for ln in lines:
            print(ln)

        portfolio = m_port.compute(df) if len(by_strat) >= 2 else None
        status.step("writing report (tables + charts)...")
        dest = m_report.write_report(reports, portfolio, args.out, cfg)

        status.step(f"DONE in {status.elapsed():.1f}s - everything saved:")
        print(f"    - report dir : {dest}")
        print(f"        summary.csv / summary.md / qualification.md")
        if portfolio is not None:
            print(f"        portfolio_correlation.png / portfolio_equity.png / mc_*.png")
        print(f"    - run log    : "
              f"{os.path.join(args.out, f'eval_run_{run_ts}.log')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

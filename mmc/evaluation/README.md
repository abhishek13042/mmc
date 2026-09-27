# `mmc.evaluation` — strategy qualification pipeline

Answers **"is this edge real and fundable?"** instead of the four vanity numbers
(WR / PF / ExpR / total-R) the console backtests print. Consumes a per-trade log
and produces the full statistical-validity → drawdown → risk-adjusted →
stability → robustness → portfolio stack, then applies **pre-committed** pass/fail
gates so a favourite strategy can't be waved through.

## Quick start

One command that does both steps (export from MT5, then evaluate):
```
python examples/mt5_oos_test.py --months 12 --evaluate
```
Or run the two steps separately (below).

## Two steps

### 1. Export trades from the live MT5 feed
```
python examples/mt5_oos_test.py --months 12          # TOP-15 fleet
python examples/mt5_oos_test.py --months 12 --all72  # every trained model
python examples/mt5_oos_test.py --spread-pips 0.20   # fixed spread (default)
```
Writes `mmc/evaluation/data/trades_<ts>.csv` and appends+dedups into
`trades_master.csv` (dedup key = `strategy_id + entry_time`), so N grows as you
re-run. Widen `--months` to clear the N≥100 sample-size gate. Every trade is
charged a **fixed 0.20-pip spread** (pip = 10× the symbol's point → ~0.00002 on
EUR/GBP, ~0.02 on XAU), overridable with `--spread-pips`.

**Resumable.** The slow part is pulling candles from MT5 and building each
feature base. Every base is cached to `data/_cache/` the moment it's built (and
tracked in `data/_export_manifest.json`), so if the run is interrupted — crash,
MT5 disconnect, Ctrl-C — just **re-run the same command** and it continues from
where it left off (`N already cached -> resuming`), re-pulling nothing it already
has. Use `--fresh` to ignore the cache and rebuild from freshly-pulled candles
(do this when you want up-to-date market data rather than resuming an old run).

**Parallel.** Candle pulls stay in the main process (one MT5 terminal
connection), but the CPU-heavy feature-base builds run across a process pool —
`--jobs N` (default `0` = auto / CPU count). This gives a real speedup on full
rebuilds (`--fresh`, `--all72`, wide `--months`) where each base is a heavy
40k-bar build; for a mostly-cached resume there's little to build so it's moot.
Workers pay a one-time import cost each, so `--jobs 1` (serial) can be faster
when only one or two small bases need building.

### 2. Evaluate
```
python -m mmc.evaluation --trades mmc/evaluation/data/trades_master.csv
```
Writes `mmc/evaluation/reports/<ts>/`:
- `summary.csv` / `summary.md` — per-strategy metric table + tier/verdict
- `qualification.md` — the four gates and each strategy's PASS/FAIL/INSUFFICIENT
- `portfolio_correlation.png`, `portfolio_equity.png`, `mc_<strategy>.png`

### Progress & saved run-logs
Both commands print a **live status line** — a timestamped `+elapsed` step for
each phase and an in-place `[####----] k/total` bar over the slow loops (feature-
base building in the exporter, bootstrap/Monte-Carlo per strategy in the
evaluator). Every run also **mirrors its console output to a log file** so nothing
is lost:
- exporter → `mmc/evaluation/data/run_<ts>.log` (+ `trades_<ts>.csv`, `trades_master.csv`)
- evaluator → `mmc/evaluation/reports/eval_run_<ts>.log` (+ the `<ts>/` report folder)

Each run ends with a `DONE in Ns - everything saved:` block listing every file
written.

## Pre-committed gates (override at the CLI)
| gate | default | flag |
| --- | --- | --- |
| sample size N | ≥ 100 | `--min-n` |
| bootstrap PF (5th pct) | > 1.2 | `--bootstrap-pf` |
| recovery factor | > 2.0 | `--recovery` |
| IS/OOS PF decay | < 30% | `--max-decay` |

Below N, tier = `INSUFFICIENT_DATA` and the rest is informational. IS/OOS decay
compares the log against the training-time in-sample numbers in
`mmc/brain/weights/RESULTS_TABLE.csv`.

## Trade-log schema (canonical)
`strategy_id, pair, combo, rr, entry_time, exit_time, direction, entry_price,
stop, take_profit, risk, score, outcome, r_multiple, spread_cost, bars_held,
split, source, run_ts` — only `strategy_id, entry_time, r_multiple` are strictly
required; the rest enrich the analysis. See `schema.py`.

## Library use
```python
from mmc.evaluation import load_trades, QualifyConfig
from mmc.evaluation.qualify import evaluate_strategy
from mmc.evaluation.schema import split_by_strategy

df = load_trades("mmc/evaluation/data/trades_master.csv")
cfg = QualifyConfig(min_n=100)
for sid, trades in split_by_strategy(df).items():
    rep = evaluate_strategy(sid, trades, cfg)
    print(sid, rep.qualification.tier.value, rep.core.profit_factor)
```

Metric definitions mirror `mmc.backtest.result.BacktestResult` for parity with
the rest of the codebase. Tests: `pytest tests/test_evaluation.py`.

"""Backtest the full top-down trade-plan cascade over thousands of candles.

Replicates examples/trade_plan.py exactly, then simulates it:
  bias (top-down filtering)  ->  H1 aligned context (usual continue / unusual
  reverse)  ->  M15 (and M5) sharp-turn + order-flow entries  ->  retarget to the
  nearest ITH/ITL (min RR 2.0)  ->  fill simulation.

Reports, per symbol and aggregated:
  trades | win% | expectancy R | profit factor | avg RR,
a confidence-bucket calibration table, and a bias-filter ON vs OFF comparison
(so we can see the top-down filter is adding edge, not a look-ahead artifact).

Usage:
    python examples/backtest_trade_plan.py [BARS]      (default 4000)

NOT financial advice.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mmc.core import Direction, find_swings  # noqa: E402
from mmc.core.structure import intermediate_term_points  # noqa: E402
from mmc.core.types import Timeframe  # noqa: E402
from mmc.context import find_context_areas, find_unusual_context  # noqa: E402
from mmc.data import load  # noqa: E402
from mmc.entry import Entry, find_entries  # noqa: E402
from mmc.backtest.engine import run_backtest  # noqa: E402
from mmc.backtest.result import BacktestResult  # noqa: E402
from mmc.topdown import top_down, TraderStyle  # noqa: E402

CONFIDENCE = {"UNUSUAL": 88, "ODD": 78, "FLOD": 65, "LOD": 65}
SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD"]
MIN_RR = 2.0
CTX_TF = Timeframe.H1
ENTRY_TFS = [Timeframe.M15, Timeframe.M5]


def _classify(area) -> str:
    return "UNUSUAL" if area.kind == "unusual" else area.defense


def _nearest_target(direction: Direction, price: float, its) -> Optional[float]:
    if direction is Direction.BULLISH:
        cands = [p for p in its if p.is_high and p.price > price]
    else:
        cands = [p for p in its if not p.is_high and p.price < price]
    return min(cands, key=lambda p: abs(p.price - price)).price if cands else None


def run_plan(symbol: str, entry_tf: Timeframe, bars: int,
             use_bias_filter: bool = True) -> BacktestResult:
    """The trade_plan cascade, simulated over `bars` of the entry timeframe."""
    ratio = max(1, CTX_TF.minutes // entry_tf.minutes)
    ctx_bars = max(bars // ratio, 300)
    ctx_df = load(symbol, CTX_TF).iloc[-ctx_bars:]
    entry_df = load(symbol, entry_tf).iloc[-bars:]
    its = intermediate_term_points(find_swings(ctx_df))

    bias = None
    if use_bias_filter:
        try:
            bias = top_down(symbol, style=TraderStyle.FILTERING_PROCESS, bars=600).direction
        except Exception:
            bias = None

    areas = find_context_areas(ctx_df) + find_unusual_context(ctx_df)
    if bias is not None:
        areas = [a for a in areas
                 if (a.kind == "usual" and a.direction is bias)
                 or (a.kind == "unusual" and a.direction is bias.opposite)]

    raw: List[Entry] = []
    for area in areas:
        for etype in ("sharp_turn", "order_flow"):
            raw.extend(find_entries(area, entry_df, entry_type=etype))

    # Dedupe (same bar + direction) and retarget to ITH/ITL, keep RR >= MIN_RR
    seen = set()
    final: List[Entry] = []
    for e in sorted(raw, key=lambda e: e.index):
        key = (e.index, e.direction)
        if key in seen:
            continue
        liq = _nearest_target(e.direction, e.entry_price, its)
        if liq is None:
            continue
        risk = abs(e.entry_price - e.stop_loss)
        if risk <= 0:
            continue
        rr = abs(liq - e.entry_price) / risk
        if rr < MIN_RR:
            continue
        if e.direction is Direction.BULLISH and liq <= e.entry_price:
            continue
        if e.direction is Direction.BEARISH and liq >= e.entry_price:
            continue
        seen.add(key)
        e.take_profit = liq
        e.rr = rr
        setup = _classify(e.context)  # each entry's OWN context, not the loop var
        e._conf = CONFIDENCE.get(setup, 60)
        e._setup = setup
        final.append(e)

    return run_backtest(final, entry_df)


def _line(label: str, r: BacktestResult) -> str:
    if r.num_trades == 0:
        return f"  {label:18} —no trades—"
    pf = r.profit_factor
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    return (f"  {label:18} {r.num_trades:4}tr  win {r.win_rate:5.1%}  "
            f"exp {r.expectancy:+5.2f}R  PF {pf_s:>5}  avgRR {r.average_rr:.1f}")


def main() -> None:
    bars = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    print("=" * 74)
    print(f"BACKTEST — full top-down trade-plan cascade   |   {bars:,} candles/leg")
    print("=" * 74)

    all_trades = []
    bias_on_trades = []
    bias_off_trades = []

    for entry_tf in ENTRY_TFS:
        print(f"\n### Entry timeframe: {entry_tf.name}  (H1 context)\n")
        for symbol in SYMBOLS:
            r = run_plan(symbol, entry_tf, bars, use_bias_filter=True)
            print(_line(symbol, r))
            for t in r.filled_trades:
                all_trades.append(t)
                bias_on_trades.append(t)
            # bias-off comparison
            r_off = run_plan(symbol, entry_tf, bars, use_bias_filter=False)
            bias_off_trades.extend(r_off.filled_trades)

    # ---- aggregate confirmation -------------------------------------------
    def stats(trades):
        n = len(trades)
        if n == 0:
            return (0, 0, 0, 0)
        wins = sum(1 for t in trades if t.is_win)
        gp = sum(t.r_multiple for t in trades if t.r_multiple > 0)
        gl = -sum(t.r_multiple for t in trades if t.r_multiple < 0)
        pf = gp / gl if gl else float("inf")
        exp = sum(t.r_multiple for t in trades) / n
        return (n, wins / n, exp, pf)

    print("\n" + "=" * 74)
    print("AGGREGATE CONFIRMATION  (all symbols, M15 + M5)")
    print("=" * 74)
    n, wr, exp, pf = stats(all_trades)
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    total_r = sum(t.r_multiple for t in all_trades)
    print(f"  trades        : {n}")
    print(f"  win rate      : {wr:.1%}")
    print(f"  expectancy    : {exp:+.2f}R per trade")
    print(f"  profit factor : {pf_s}")
    print(f"  total         : {total_r:+.1f}R")

    # ---- calibration by confidence ----------------------------------------
    print("\n  Confidence calibration:")
    print(f"  {'conf':>6} {'trades':>7} {'win%':>7} {'exp(R)':>8} {'PF':>6}")
    buckets: Dict[int, list] = {}
    for t in all_trades:
        buckets.setdefault(getattr(t.entry, "_conf", 0), []).append(t)
    for c in sorted(buckets, reverse=True):
        n, wr, exp, pf = stats(buckets[c])
        pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
        print(f"  {c:>5}% {n:>7} {wr:>6.1%} {exp:>+7.2f} {pf_s:>6}")

    # ---- bias filter ON vs OFF --------------------------------------------
    print("\n  Top-down bias filter — does it add edge?")
    for label, trades in (("bias ON", bias_on_trades), ("bias OFF", bias_off_trades)):
        n, wr, exp, pf = stats(trades)
        pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
        print(f"    {label:9}: {n:5} tr  win {wr:5.1%}  exp {exp:+.2f}R  PF {pf_s}")

    print("\n" + "=" * 74)
    print("Note: top-down bias is computed once over the recent window (mild")
    print("look-ahead, same simplification as the other runners). The bias ON/OFF")
    print("comparison shows whether the filter is doing real work.")


if __name__ == "__main__":
    main()

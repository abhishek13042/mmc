"""Run all 7 MMC strategies across multiple timeframe combinations.

Usage:
    python examples/run_all_strategies.py [SYMBOL] [BARS]

Defaults: EURUSD, 1000 bars.

Timeframe combos tested (context TF → entry TF):
  D1→H4  |  H4→H1  |  H1→M15  |  M15→M5

Each cell shows:  trades | win% | expectancy R | PF
Target for every trade is the nearest ITH (bullish) or ITL (bearish) —
the real liquidity level the market is heading toward per the narrative.

NOT financial advice.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mmc.backtest.result import BacktestResult
from mmc.core.types import Timeframe
from mmc.strategies import (
    TF_COMBOS,
    s1_filtering_process,
    s2_flow_trader,
    s3_flod,
    s4_odd,
    s5_unusual_context,
    s6_turtle_soup,
    s7_lod_swing_sweep,
)


def _parse_args() -> Tuple[str, int]:
    symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "EURUSD"
    bars   = int(sys.argv[2])    if len(sys.argv) > 2 else 1_000
    return symbol, bars


def _cell(r: BacktestResult) -> str:
    """Compact cell: trades|win%|avgRR|exp|PF"""
    if r.num_trades == 0:
        return "  —no trades—     "
    pf = r.profit_factor
    pf_s = " inf" if pf == float("inf") else f"{pf:.2f}"
    return (
        f"{r.num_trades:>3}tr "
        f"{r.win_rate:>5.1%} "
        f"RR{r.average_rr:>4.1f} "
        f"{r.expectancy:>+5.2f}R "
        f"PF{pf_s}"
    )


def _run_safe(fn: Callable[[], BacktestResult]) -> Tuple[Optional[BacktestResult], float, str]:
    t0 = time.time()
    try:
        r = fn()
        return r, time.time() - t0, ""
    except Exception as e:
        return None, time.time() - t0, str(e)


def main() -> None:
    symbol, bars = _parse_args()

    combos = TF_COMBOS      # (ctx_tf, entry_tf, label)
    col_w  = 34             # cell column width

    header = f"MMC — 7 Strategies × {len(combos)} TF combos  |  {symbol}  |  {bars:,} bars"
    print(f"\n{header}")
    print("=" * (22 + col_w * len(combos)))

    # Column headers
    print(f"  {'Strategy':<20}", end="")
    for _, _, lbl in combos:
        print(f"  {lbl:<{col_w}}", end="")
    print()
    print("-" * (22 + col_w * len(combos)))

    # S1 — filtering process (always D1→H4 for the bias pass + user-chosen entry TF)
    strategies: List[Tuple[str, Callable[[], BacktestResult]]] = []

    for ctx_tf, entry_tf, lbl in combos:
        strategies.append((
            lbl,
            lambda c=ctx_tf, e=entry_tf: s1_filtering_process(
                symbols=[symbol], bars=bars, ctx_tf=c, entry_tf=e
            ),
        ))

    print(f"  {'S1 Filtering Proc':<20}", end="")
    for _, fn in strategies:
        r, t, err = _run_safe(fn)
        if r:
            print(f"  {_cell(r):<{col_w}}", end="")
        else:
            print(f"  {'ERR:'+err[:20]:<{col_w}}", end="")
    print()

    # S2 — flow trader
    print(f"  {'S2 Flow Trader':<20}", end="")
    for ctx_tf, entry_tf, _ in combos:
        r, t, err = _run_safe(
            lambda c=ctx_tf, e=entry_tf: s2_flow_trader(symbol, bars, ctx_tf=c, entry_tf=e)
        )
        print(f"  {_cell(r) if r else 'ERR':<{col_w}}", end="")
    print()

    # S3–S7: each runs independently per TF combo
    remaining = [
        ("S3 FLOD",         s3_flod),
        ("S4 ODD",          s4_odd),
        ("S5 Unusual Ctx",  s5_unusual_context),
        ("S6 Turtle Soup",  s6_turtle_soup),
        ("S7 LOD Sweep",    s7_lod_swing_sweep),
    ]

    for name, fn in remaining:
        print(f"  {name:<20}", end="")
        for ctx_tf, entry_tf, _ in combos:
            r, t, err = _run_safe(
                lambda c=ctx_tf, e=entry_tf, f=fn: f(symbol, bars, ctx_tf=c, entry_tf=e)
            )
            print(f"  {_cell(r) if r else 'ERR:'+err[:18]:<{col_w}}", end="")
        print()

    print("-" * (22 + col_w * len(combos)))
    print("\nEach cell: trades | win% | avg RR | expectancy R | profit factor")
    print("TP = nearest ITH (bullish) or ITL (bearish) = real liquidity target  (min RR: 2.0)")
    print("SL = above/below order flow lag.  All trades: limit order simulation.\n")


if __name__ == "__main__":
    main()

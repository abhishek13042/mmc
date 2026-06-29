"""Full MMC top-down → an actionable M15/M5 trade plan.

Walks the exact cascade Arjo teaches (transcripts 12 → 11):

  1. DIRECTION  — filtering process across pairs picks the highest-probability
                  pair and its bias (read on D1/H4).
  2. NARRATIVE  — on H1, the most recent context area aligned with the bias
                  (usual = continue; unusual = reversal), and the liquidity it
                  targets (nearest ITH / ITL).
  3. ENTRY      — on M15 (drop to M5 if M15 has none) a sharp-turn FVG inside
                  that context area: entry / stop / target / RR / confidence.

Usage:
    python examples/trade_plan.py [SYMBOL ...]

With no symbols it runs the filtering process over EURUSD, GBPUSD, XAUUSD and
trades the winner. Give one symbol to force it.

NOT financial advice. Computed on the most recent cached bar, not a live feed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

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
from mmc.topdown import best_pair, top_down, TraderStyle  # noqa: E402

CONFIDENCE = {"UNUSUAL": 88, "ODD": 78, "FLOD": 65, "LOD": 65}
DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD"]
MIN_RR = 2.0


def _fmt(p: float, symbol: str) -> str:
    return f"{p:,.2f}" if symbol == "XAUUSD" else f"{p:.5f}"


def _classify(area) -> str:
    return "UNUSUAL" if area.kind == "unusual" else area.defense


def _nearest_target(direction: Direction, price: float, its) -> Optional[float]:
    if direction is Direction.BULLISH:
        cands = [p for p in its if p.is_high and p.price > price]
    else:
        cands = [p for p in its if not p.is_high and p.price < price]
    return min(cands, key=lambda p: abs(p.price - price)).price if cands else None


def _retarget(e: Entry, its) -> Optional[Entry]:
    """Patch TP to the nearest ITH/ITL giving RR >= MIN_RR. None if not tradeable."""
    liq = _nearest_target(e.direction, e.entry_price, its)
    if liq is None:
        return None
    risk = abs(e.entry_price - e.stop_loss)
    if risk <= 0:
        return None
    rr = abs(liq - e.entry_price) / risk
    if rr < MIN_RR:
        return None
    if e.direction is Direction.BULLISH and liq <= e.entry_price:
        return None
    if e.direction is Direction.BEARISH and liq >= e.entry_price:
        return None
    e.take_profit = liq
    e.rr = rr
    return e


def step1_direction(symbols: List[str]):
    print("STEP 1 — DIRECTION  (filtering process across pairs, read on D1/H4)")
    print("-" * 66)
    rows = []
    for s in symbols:
        try:
            td = top_down(s, style=TraderStyle.FILTERING_PROCESS, bars=600)
            rows.append((s, td.direction, td.probability, td.one_sided))
        except Exception as exc:
            rows.append((s, None, 0.0, False))
            print(f"  {s}: error ({exc})")
    for s, d, prob, one in sorted(rows, key=lambda r: r[2], reverse=True):
        if d is None:
            continue
        flag = "one-sided" if one else "mixed"
        print(f"  {s:7} {d.name:8} probability {prob:.2f}  ({flag})")

    if len(symbols) == 1:
        picked_sym, picked_dir = rows[0][0], rows[0][1]
    else:
        rp = best_pair(symbols, style=TraderStyle.FILTERING_PROCESS, bars=600)
        picked_sym = rp.symbol if rp else rows[0][0]
        picked_dir = rp.direction if rp else rows[0][1]
    print(f"\n  >> Highest probability: {picked_sym} {picked_dir.name if picked_dir else 'n/a'}")
    return picked_sym, picked_dir


def step2_narrative(symbol: str, bias: Direction):
    print("\nSTEP 2 — NARRATIVE + CONTEXT  (H1)")
    print("-" * 66)
    h1 = load(symbol, Timeframe.H1).iloc[-1500:]
    price = float(h1["close"].to_numpy()[-1])
    its = intermediate_term_points(find_swings(h1))

    areas = find_context_areas(h1) + find_unusual_context(h1)
    tradeable = [a for a in areas
                 if (a.kind == "usual" and a.direction is bias)
                 or (a.kind == "unusual" and a.direction is bias.opposite)]
    tradeable.sort(key=lambda a: a.boundary.index)
    recent = tradeable[-8:]  # the most recent aligned contexts we still hunt in

    latest = max(areas, key=lambda a: a.boundary.index) if areas else None
    if latest is not None and latest.kind == "unusual" and latest.direction is bias.opposite:
        print("  [!] Latest H1 signal is UNUSUAL context against bias — reversal in play.")

    if not recent:
        print(f"  No bias-aligned H1 context yet. Price {_fmt(price, symbol)}.")
        return [], its, price

    setups = {}
    for a in recent:
        setups[_classify(a)] = setups.get(_classify(a), 0) + 1
    area = recent[-1]
    tgt = _nearest_target(area.direction, price, its)
    print(f"  Price {_fmt(price, symbol)}   bias {bias.name}")
    print(f"  {len(recent)} recent aligned contexts: "
          + ", ".join(f"{k}x{v}" for k, v in setups.items()))
    print(f"  Most recent: {_classify(area)} ({CONFIDENCE.get(_classify(area), 0)}%), "
          f"boundary {_fmt(area.boundary.bottom, symbol)}–{_fmt(area.boundary.top, symbol)}")
    if tgt is not None:
        print(f"  Liquidity draw: {_fmt(tgt, symbol)}  "
              f"({'ITH / sell-side' if area.direction is Direction.BULLISH else 'ITL / buy-side'})")
    return recent, its, price


def step3_entry(symbol: str, areas, its):
    print("\nSTEP 3 — ENTRY  (M15, drop to M5 if none)")
    print("-" * 66)
    if not areas:
        print("  No context to look for entries in — STAND ASIDE.")
        return

    for tf in (Timeframe.M15, Timeframe.M5):
        edf = load(symbol, tf).iloc[-4000:]
        cands: List[Entry] = []
        for area in areas:
            for etype in ("sharp_turn", "order_flow"):
                for e in find_entries(area, edf, entry_type=etype):
                    re = _retarget(e, its)
                    if re:
                        cands.append(re)
        if not cands:
            print(f"  {tf.name}: no entry inside the recent contexts yet.")
            continue
        e = max(cands, key=lambda e: e.index)  # freshest
        bars_ago = len(edf) - 1 - e.index
        ts = edf.index[e.index]
        setup = _classify(e.context)
        fresh = "FRESH — actionable" if bars_ago <= 12 else f"stale — last was {bars_ago} bars ago"
        print(f"  {tf.name}: {len(cands)} entries in window; freshest {bars_ago} bars ago ({ts}) [{fresh}]")
        print()
        print("  ===== TRADE PLAN ===================================")
        print(f"   Symbol     : {symbol}")
        print(f"   Direction  : {e.direction.name}  "
              f"({'BUY' if e.direction is Direction.BULLISH else 'SELL'})")
        print(f"   Entry      : {_fmt(e.entry_price, symbol)}  ({e.entry_type} FVG on {tf.name})")
        print(f"   Stop loss  : {_fmt(e.stop_loss, symbol)}  (beyond the order-flow lag)")
        print(f"   Target     : {_fmt(e.take_profit, symbol)}  (ITH/ITL liquidity)")
        print(f"   Reward:Risk: {e.rr:.1f}R")
        print(f"   Confidence : {CONFIDENCE.get(setup, 0)}%  ({setup} context)")
        print(f"   Fast turn  : {'yes' if e.fast else 'no'}")
        print("  ====================================================")
        if bars_ago > 12:
            print("   NOTE: freshest entry is not recent — treat as the *pattern* to wait")
            print("   for; act when price next delivers into a boundary and prints this.")
        return
    print("  No M15 or M5 entry inside the recent contexts — WAIT for price to "
          "deliver into a boundary and print a sharp turn.")


def main() -> None:
    symbols = [a.upper() for a in sys.argv[1:]] or DEFAULT_SYMBOLS
    print("=" * 66)
    print("MMC TOP-DOWN  ->  M15/M5 TRADE PLAN")
    print("=" * 66)
    sym, bias = step1_direction(symbols)
    if bias is None:
        print("\nNo directional read — stand aside.")
        return
    areas, its, price = step2_narrative(sym, bias)
    step3_entry(sym, areas, its)
    print("\n(Computed on the most recent cached bar — not a live feed.)")


if __name__ == "__main__":
    main()

"""Predict the next liquidity draw — which ITH/ITL price is being hunted.

Runs the MMC "brain" against the most recent bar in the data and calls, for each
symbol: the top-down bias, the liquidity map (nearest sell-side ITHs above and
buy-side ITLs below), and the predicted draw on liquidity — the specific ITH
(bullish) or ITL (bearish) price the market is heading toward, with the RR from
the current price and the most recent context area that confirms it.

Usage:
    python examples/predict_liquidity.py [SYMBOL ...] [--tf H1]

Examples:
    python examples/predict_liquidity.py
    python examples/predict_liquidity.py XAUUSD --tf H4

NOT financial advice. Targets are computed on the most recent bar available in
the cached data (printed as "as of ..."), not a live market feed.
"""

from __future__ import annotations

import sys
from pathlib import Path

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
from mmc.topdown import top_down, TraderStyle  # noqa: E402

CONFIDENCE = {"UNUSUAL": 88, "ODD": 78, "FLOD": 65, "LOD": 65}
DEFAULT_SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD"]
MIN_RR = 2.0


def _classify(area) -> str:
    return "UNUSUAL" if area.kind == "unusual" else area.defense


def _fmt(p: float, symbol: str) -> str:
    return f"{p:,.2f}" if symbol == "XAUUSD" else f"{p:.5f}"


def predict(symbol: str, ctx_tf: Timeframe = Timeframe.H1) -> None:
    df = load(symbol, ctx_tf).iloc[-1500:]
    last_ts = df.index[-1]
    price = float(df["close"].to_numpy()[-1])

    its = intermediate_term_points(find_swings(df))
    iths = sorted([p for p in its if p.is_high and p.price > price], key=lambda p: p.price)
    itls = sorted([p for p in its if not p.is_high and p.price < price],
                  key=lambda p: p.price, reverse=True)

    try:
        bias = top_down(symbol, style=TraderStyle.FILTERING_PROCESS, bars=600).direction
    except Exception:
        bias = None

    print("=" * 66)
    print(f"{symbol}   as of {last_ts}   price {_fmt(price, symbol)}   "
          f"bias {bias.name if bias else 'n/a'}")
    print("  Liquidity map:")
    print("    sell-side above (ITH): " +
          (", ".join(_fmt(p.price, symbol) for p in iths[:3]) if iths else "none"))
    print("    buy-side  below (ITL): " +
          (", ".join(_fmt(p.price, symbol) for p in itls[:3]) if itls else "none"))

    if bias is None:
        print("  --> no bias available")
        return

    # Invalidation = nearest opposing swing a meaningful distance away (skip swings
    # sitting on top of price, which would give a degenerate risk).
    min_dist = price * 0.0008
    opposing = itls if bias is Direction.BULLISH else iths
    levels = iths if bias is Direction.BULLISH else itls
    if not levels:
        side = "ITH above" if bias is Direction.BULLISH else "ITL below"
        print(f"  --> bias {bias.name} but no {side} to target.")
        return
    stop_pool = next((p.price for p in opposing if abs(price - p.price) >= min_dist),
                     opposing[-1].price if opposing else price)
    risk = abs(price - stop_pool)

    # Nearest liquidity level giving RR >= MIN_RR, else the furthest draw.
    target = next((lv for lv in levels
                   if risk > 0 and abs(lv.price - price) / risk >= MIN_RR), levels[-1])
    rr = abs(target.price - price) / risk if risk > 0 else float("inf")

    # Supporting context the brain would actually trade (usual aligned / unusual reversed).
    areas = find_context_areas(df) + find_unusual_context(df)
    support = next((a for a in sorted(areas, key=lambda a: a.boundary.index, reverse=True)
                    if (a.kind == "usual" and a.direction is bias)
                    or (a.kind == "unusual" and a.direction is bias.opposite)), None)
    latest = max(areas, key=lambda a: a.boundary.index) if areas else None
    reversal_warn = latest is not None and latest.kind == "unusual" \
        and latest.direction is bias.opposite

    draw = "UP -> sell-side (ITH)" if bias is Direction.BULLISH else "DOWN -> buy-side (ITL)"
    print(f"  --> PREDICTION: price is drawing {draw}")
    print(f"      Target liquidity : {_fmt(target.price, symbol)}   "
          f"({rr:.1f}R from here, risk at {_fmt(stop_pool, symbol)})")
    if support:
        s = _classify(support)
        print(f"      Confirmed by     : most recent {s} context "
              f"({CONFIDENCE.get(s, 0)}% confidence), aligned with bias")
    else:
        print("      Confirmed by     : no bias-aligned context yet — wait for a setup")
    if reversal_warn:
        print("      [!] REVERSAL WATCH: latest signal is UNUSUAL context against bias "
              "(88%) — price may hunt the opposite side first")


def main() -> None:
    args = [a for a in sys.argv[1:]]
    ctx_tf = Timeframe.H1
    if "--tf" in args:
        i = args.index("--tf")
        ctx_tf = Timeframe[args[i + 1].upper()]
        del args[i:i + 2]
    symbols = [a.upper() for a in args] or DEFAULT_SYMBOLS
    for s in symbols:
        predict(s, ctx_tf)
    print("=" * 66)
    print("Targets computed on the most recent cached bar — not a live feed.")


if __name__ == "__main__":
    main()

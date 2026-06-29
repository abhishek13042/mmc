"""Scan for current MMC setups on a symbol — a decision-support tool.

It runs the full top-down (transcript 12) to get the bias + high-probability
context areas, then looks for entries (transcript 11) on a lower entry timeframe
inside the most recent context areas, printing each setup with entry / stop /
target / RR so you can place the order yourself.

Usage:
    python examples/scan_setups.py [SYMBOL] [CONTEXT_TF] [ENTRY_TF]

Examples:
    python examples/scan_setups.py EURUSD H4 M15
    python examples/scan_setups.py XAUUSD H1 M5

NOT financial advice. This is research/analysis tooling built from the MMC
transcripts; validate with the backtester before risking real money.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    sys.stdout.reconfigure(encoding="utf-8")  # clean dashes on Windows consoles
except Exception:
    pass

from mmc.context import find_context_areas  # noqa: E402
from mmc.core.types import Timeframe  # noqa: E402
from mmc.data import load  # noqa: E402
from mmc.entry import find_entries  # noqa: E402
from mmc.topdown import top_down, TraderStyle  # noqa: E402

RECENT_CONTEXTS = 5   # how many of the most recent context areas to scan
ENTRY_TYPE = "sharp_turn"


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "EURUSD"
    ctx_tf = Timeframe[sys.argv[2]] if len(sys.argv) > 2 else Timeframe.H4
    entry_tf = Timeframe[sys.argv[3]] if len(sys.argv) > 3 else Timeframe.M15

    # 1) Bias / direction (top-down across the higher timeframes).
    td = top_down(symbol, style=TraderStyle.FILTERING_PROCESS, bars=600)
    print(f"\n{symbol}  —  {td.bias.summary}")
    print(f"Direction: {td.direction.name}   (probability {td.probability:.2f})\n")

    # 2) High-probability context areas on the context timeframe, aligned to bias.
    ctx_df = load(symbol, ctx_tf).iloc[-600:]
    areas = [a for a in find_context_areas(ctx_df) if a.direction is td.direction]
    areas = areas[-RECENT_CONTEXTS:]
    if not areas:
        print(f"No {td.direction.name.lower()} context areas on {ctx_tf.name} right now.")
        return

    # 3) Entries inside each context area, on the lower entry timeframe.
    entry_df = load(symbol, entry_tf).iloc[-3000:]
    found = 0
    for area in areas:
        entries = find_entries(area, entry_df, entry_type=ENTRY_TYPE)
        for e in entries[-3:]:                     # most recent few per area
            ts = entry_df.index[e.index]
            found += 1
            print(
                f"  [{e.direction.name:7s}] {ts}  "
                f"entry {e.entry_price:.5f}  SL {e.stop_loss:.5f}  "
                f"TP {e.take_profit:.5f}  ({e.rr:.0f}R"
                f"{', fast' if e.fast else ''})"
            )

    if not found:
        print(f"{len(areas)} context area(s) found, but no {ENTRY_TYPE} entries "
              f"on {entry_tf.name} yet — wait for price to deliver into a boundary.")
    else:
        print(f"\n{found} candidate setup(s). Confirm on your chart before acting.")


if __name__ == "__main__":
    main()

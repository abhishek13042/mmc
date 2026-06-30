"""Brain v2 — train the decision brain on mmc + atoz concepts and report which
library's features carry the edge.

v2 = the 31 mmc engine features (v1) + 24 atoz ICT A-Z Guide features, on the
SAME FVG-tap setups and labels, so the comparison isolates what the second
knowledge base adds.

Usage:
    python examples/run_brain_v2.py                    # EURUSD H4->H1
    python examples/run_brain_v2.py --symbol GBPUSD
    python examples/run_brain_v2.py --all              # pool EUR+GBP+XAU
    python examples/run_brain_v2.py --limit 8000       # faster first run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mmc.brain.dataset_v2 import build_dataset_v2, build_all_datasets_v2
from mmc.brain.features import FEATURE_NAMES
from mmc.brain.features_v2 import FEATURE_NAMES_V2
from mmc.brain.atoz_features import ATOZ_FEATURE_NAMES
from mmc.brain.train_v2 import compare_architectures_cols, perceptron_weights
from mmc.core.types import Timeframe


def _print_weights(weights: dict, title: str) -> None:
    ranked = sorted(weights.items(), key=lambda kv: abs(kv[1]), reverse=True)
    print(f"\n{title}")
    print(f"{'Feature':<22}{'src':>5}{'weight':>10}")
    print("-" * 45)
    for name, w in ranked[:20]:
        src = "atoz" if name in ATOZ_FEATURE_NAMES else "mmc"
        bar = "#" * int(min(abs(w), 3.0) * 12)
        sign = "+" if w >= 0 else "-"
        print(f"{name:<22}{src:>5}  {sign}{abs(w):>7.4f}  {bar}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument("--all", action="store_true", help="pool EURUSD+GBPUSD+XAUUSD")
    ap.add_argument("--limit", type=int, default=None, help="use only last N entry bars")
    ap.add_argument("--context", default="H4")
    ap.add_argument("--entry", default="H1")
    args = ap.parse_args()

    ctx_tf = Timeframe[args.context]
    ent_tf = Timeframe[args.entry]

    print("=" * 60)
    print("  BRAIN v2 — mmc (31) + atoz (24) = 55 concept features")
    print("=" * 60)

    if args.all:
        ds = build_all_datasets_v2(context_tf=ctx_tf, entry_tf=ent_tf, limit_bars=args.limit)
    else:
        ds = build_dataset_v2(args.symbol, context_tf=ctx_tf, entry_tf=ent_tf, limit_bars=args.limit)

    if ds.empty or len(ds) < 30:
        print(f"\nNot enough setups ({0 if ds.empty else len(ds)}). Try a larger window.")
        return

    # --- v1 baseline: mmc features only -----------------------------------
    print("\n" + "-" * 60)
    print("  [A] v1 baseline — mmc features only (31)")
    print("-" * 60)
    res_v1, _ = compare_architectures_cols(ds, feature_cols=FEATURE_NAMES, verbose=True)

    # --- v2: combined mmc + atoz ------------------------------------------
    print("\n" + "-" * 60)
    print("  [B] v2 — mmc + atoz combined (55)")
    print("-" * 60)
    res_v2, perceptron = compare_architectures_cols(ds, feature_cols=FEATURE_NAMES_V2, verbose=True)

    # --- side-by-side ------------------------------------------------------
    print("\n" + "=" * 60)
    print("  RESULT — v1 (mmc) vs v2 (mmc+atoz), same setups")
    print("=" * 60)
    print(f"{'arch':<12}{'v1 WR':>8}{'v2 WR':>8}{'v1 PF':>8}{'v2 PF':>8}")
    print("-" * 44)
    for arch in res_v1.index:
        print(f"{arch:<12}"
              f"{res_v1.loc[arch,'win_rate']:>7.1%}"
              f"{res_v2.loc[arch,'win_rate']:>8.1%}"
              f"{res_v1.loc[arch,'profit_factor']:>8.2f}"
              f"{res_v2.loc[arch,'profit_factor']:>8.2f}")

    # --- which concepts the brain values (readable perceptron weights) ----
    if perceptron is not None:
        weights = perceptron_weights(perceptron, FEATURE_NAMES_V2)
        _print_weights(weights, "Top concepts by |weight| (v2 perceptron)")

        atoz_w = {k: v for k, v in weights.items() if k in ATOZ_FEATURE_NAMES}
        top_atoz = sorted(atoz_w.items(), key=lambda kv: abs(kv[1]), reverse=True)[:8]
        print("\nTop atoz concepts that earned weight:")
        for name, w in top_atoz:
            print(f"  {name:<22} {'+' if w >= 0 else '-'}{abs(w):.4f}")


if __name__ == "__main__":
    main()

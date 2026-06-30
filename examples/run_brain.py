"""Run the MMC decision brain — compare 3 architectures on EURUSD/GBPUSD/XAUUSD.

Usage:
    python examples/run_brain.py
    python examples/run_brain.py --symbol GBPUSD
    python examples/run_brain.py --all          # all 3 symbols
    python examples/run_brain.py --weights      # show perceptron feature weights
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mmc.brain import (
    build_all_datasets,
    build_dataset,
    compare_architectures,
    get_model,
    print_feature_importance,
    run_brain,
)
from mmc.brain.train import train_model, walk_forward_split
from mmc.core.types import Timeframe


def main():
    parser = argparse.ArgumentParser(description="MMC Decision Brain")
    parser.add_argument("--symbol", default="EURUSD", help="Symbol to train on")
    parser.add_argument("--all",     action="store_true", help="Train on all symbols")
    parser.add_argument("--weights", action="store_true", help="Show perceptron weights")
    parser.add_argument("--tf", default="H4->H1", help="Context->Entry timeframes (H4->H1 or D1->H4)")
    args = parser.parse_args()

    # Parse timeframes
    tf_map = {
        "H4": Timeframe.H4, "H1": Timeframe.H1,
        "D1": Timeframe.D1, "M15": Timeframe.M15,
    }
    ctx_name, entry_name = args.tf.split("->")
    ctx_tf   = tf_map[ctx_name]
    entry_tf = tf_map[entry_name]

    print("=" * 60)
    print("  MMC Decision Brain")
    print(f"  Concepts: 11 A-Z lectures + liquidity masterclass")
    print(f"  Features: 31 named concept signals")
    print(f"  Architectures: Perceptron | ShallowNN | DeepNN")
    print(f"  TF cascade: {ctx_name} context → {entry_name} entry")
    print("=" * 60)

    # Build dataset
    symbols = ["EURUSD", "GBPUSD", "XAUUSD"] if args.all else [args.symbol]

    if args.all:
        dataset = build_all_datasets(symbols, ctx_tf, entry_tf)
    else:
        dataset = build_dataset(args.symbol, ctx_tf, entry_tf)

    if dataset.empty:
        print("\nNo setups detected. Possible reasons:")
        print("  - Entry detection threshold too strict")
        print("  - Data range too short")
        print("  - Context detection returning no areas")
        sys.exit(1)

    # Compare all 3 architectures
    print()
    results = compare_architectures(dataset, verbose=True)

    print("\n" + "=" * 60)
    print("  Results Summary")
    print("=" * 60)
    print(results[["win_rate", "profit_factor", "n_trades", "n_params", "best_epoch"]]
          .to_string())

    # Best architecture
    best = results["profit_factor"].idxmax()
    print(f"\n  Best architecture: {best} (PF={results.loc[best,'profit_factor']:.2f})")

    # Show perceptron weights if requested
    if args.weights:
        print("\n[Perceptron weights — what the brain learned about each concept]")
        train_df, val_df, test_df = walk_forward_split(
            dataset.sort_values("entry_time").reset_index(drop=True)
        )
        model = get_model("perceptron")
        train_model(model, train_df, val_df, verbose=False if hasattr(train_model, 'verbose') else True)
        print_feature_importance(model)

    print()


if __name__ == "__main__":
    main()

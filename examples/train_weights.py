"""Train perceptron for EURUSD across 4 TF combos and save weights permanently.

Run once:
    python examples/train_weights.py

Weights saved to:
    mmc/brain/weights/EURUSD_{ctx}_{entry}.json   <- human-readable weights + metadata
    mmc/brain/weights/EURUSD_{ctx}_{entry}.pt     <- PyTorch state for live inference

Combos trained:
    H4  -> H1   (swing context,  hourly entries)
    H1  -> M15  (hourly context, 15-min entries)
    M15 -> M5   (15-min context, 5-min entries)
    H4  -> M15  (swing context,  15-min entries)
"""
import sys, os, json, pickle, warnings
from datetime import datetime
warnings.filterwarnings("ignore")
sys.path.insert(0, "D:/MMC")

import numpy as np
import torch

from mmc.core.types import Timeframe
from mmc.brain.dataset_v2 import build_dataset_v2
from mmc.brain.features_v2 import FEATURE_NAMES_V2
from mmc.brain.architectures import get_model
from mmc.brain.train import walk_forward_split
from mmc.brain.train_v2 import train_model_cols, evaluate_model_cols, perceptron_weights

SYMBOL      = "EURUSD"
N_SEEDS     = 5
WEIGHTS_DIR = "D:/MMC/mmc/brain/weights"
CACHE_DIR   = "D:/MMC/mmc/brain/weights/_cache"

# Old scratchpad cache from validate_v2.py -- reuse if present (saves ~14s rebuild)
_OLD_CACHE  = "C:/Users/Admin/AppData/Local/Temp/claude/D--MMC/5d158628-9414-4b91-8227-583956c579b6/scratchpad"

# (context_tf, entry_tf, limit_bars, label)
# limit_bars caps the ENTRY timeframe so precompute stays fast.
# Each combo uses the most-recent bars, which keeps the HTF daily-bias slice small.
COMBOS = [
    (Timeframe.H4,  Timeframe.H1,  10_000, "H4_H1"),
    (Timeframe.H1,  Timeframe.M15, 20_000, "H1_M15"),
    (Timeframe.M15, Timeframe.M5,  20_000, "M15_M5"),
    (Timeframe.H4,  Timeframe.M15, 20_000, "H4_M15"),
]


# ---------------------------------------------------------------------------
# Dataset helpers
# ---------------------------------------------------------------------------

def _load_or_build(ctx_tf, entry_tf, limit_bars, label):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = f"{CACHE_DIR}/{SYMBOL}_{label}.pkl"

    # reuse old scratchpad cache for H4->H1 if present
    old = f"{_OLD_CACHE}/ds_v2_{SYMBOL}.pkl"
    if label == "H4_H1" and not os.path.exists(cache) and os.path.exists(old):
        print(f"  [cache] reusing previous session cache for {label}")
        ds = pickle.load(open(old, "rb"))
        pickle.dump(ds, open(cache, "wb"))
        return ds

    if os.path.exists(cache):
        print(f"  [cache] {label}")
        return pickle.load(open(cache, "rb"))

    print(f"  [build] {ctx_tf.name}->{entry_tf.name}  limit={limit_bars:,} bars")
    ds = build_dataset_v2(SYMBOL, ctx_tf, entry_tf, limit_bars=limit_bars, verbose=True)
    if not ds.empty:
        pickle.dump(ds, open(cache, "wb"))
    return ds


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def _train_best_seed(ds):
    """Train N_SEEDS perceptrons, return the one with the best test WR."""
    cols = FEATURE_NAMES_V2
    d = ds.sort_values("entry_time").reset_index(drop=True)
    tr, vl, te = walk_forward_split(d)

    best_wr, best_model, best_metrics, best_seed = -1.0, None, None, 0
    for seed in range(N_SEEDS):
        torch.manual_seed(seed)
        np.random.seed(seed)
        m = get_model("perceptron", n_features=len(cols))
        torch.manual_seed(seed)
        train_model_cols(m, tr, vl, cols, epochs=150, patience=20)
        met = evaluate_model_cols(m, te, cols)
        wr = met["win_rate"]
        print(f"    seed {seed}:  WR={wr:.1%}  PF={met['profit_factor']:.2f}  "
              f"trades={met['n_trades']}/{met['n_total']}")
        if wr > best_wr:
            best_wr, best_model, best_metrics, best_seed = wr, m, met, seed

    return best_model, best_metrics, best_seed


# ---------------------------------------------------------------------------
# Weight I/O
# ---------------------------------------------------------------------------

def _save(label, ctx_tf, entry_tf, limit_bars, ds, model, metrics, seed):
    os.makedirs(WEIGHTS_DIR, exist_ok=True)
    cols = FEATURE_NAMES_V2
    w = perceptron_weights(model, cols)

    # sort by |weight| descending -- most important features first
    ranked = sorted(w.items(), key=lambda x: abs(x[1]), reverse=True)

    payload = {
        "symbol":        SYMBOL,
        "context_tf":    ctx_tf.name,
        "entry_tf":      entry_tf.name,
        "trained_date":  datetime.now().strftime("%Y-%m-%d"),
        "limit_bars":    limit_bars,
        "n_setups":      len(ds),
        "n_seeds_tried": N_SEEDS,
        "best_seed":     seed,
        "baseline_wr":   round(float(ds["label"].mean()), 4),
        "win_rate":      metrics["win_rate"],
        "profit_factor": metrics["profit_factor"],
        "n_trades":      metrics["n_trades"],
        "n_test":        metrics["n_total"],
        # ordered list (most important first)
        "feature_names": [k for k, _ in ranked],
        "weights":       [round(v, 6) for _, v in ranked],
        # dict for direct lookup by name
        "weight_map":    {k: round(v, 6) for k, v in ranked},
    }

    json_path = f"{WEIGHTS_DIR}/{SYMBOL}_{label}.json"
    pt_path   = f"{WEIGHTS_DIR}/{SYMBOL}_{label}.pt"

    with open(json_path, "w") as f:
        json.dump(payload, f, indent=2)
    torch.save(model.state_dict(), pt_path)

    return json_path, pt_path


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _print_weights(w_map, n=15):
    items = sorted(w_map.items(), key=lambda x: abs(x[1]), reverse=True)[:n]
    src_tag = lambda k: "atoz" if k.startswith("az_") else " mmc"
    print(f"  {'Feature':<28} {'src':>4}  {'Weight':>8}")
    print(f"  {'-'*45}")
    for feat, wt in items:
        bar  = "#" * min(int(abs(wt) * 10), 20)
        sign = "+" if wt >= 0 else "-"
        print(f"  {feat:<28} {src_tag(feat)}  {sign}{abs(wt):>6.4f}  {bar}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print(f"  {SYMBOL} weight training  --  {len(COMBOS)} combos x {N_SEEDS} seeds")
    print(f"  Output: {WEIGHTS_DIR}/")
    print("=" * 60)

    summary = []
    for ctx_tf, entry_tf, limit_bars, label in COMBOS:
        print(f"\n{'-'*60}")
        print(f"  {ctx_tf.name} -> {entry_tf.name}   [{label}]")
        print(f"{'-'*60}")

        ds = _load_or_build(ctx_tf, entry_tf, limit_bars, label)
        if ds.empty:
            print("  !! No setups -- skipping")
            continue

        base_wr = 100 * ds["label"].mean()
        print(f"  {len(ds):,} setups  |  baseline WR {base_wr:.1f}%")
        print(f"  Training {N_SEEDS} seeds...")

        model, metrics, seed = _train_best_seed(ds)
        json_path, pt_path   = _save(label, ctx_tf, entry_tf, limit_bars,
                                      ds, model, metrics, seed)
        w_map = perceptron_weights(model, FEATURE_NAMES_V2)

        print(f"\n  Best (seed {seed}):  WR={metrics['win_rate']:.1%}  "
              f"PF={metrics['profit_factor']:.2f}  "
              f"trades={metrics['n_trades']}/{metrics['n_total']}")
        print(f"  Saved: {json_path}")
        print(f"         {pt_path}")
        print(f"\n  Top 15 weights:")
        _print_weights(w_map)

        summary.append({
            "label":   label,
            "setups":  len(ds),
            "base_wr": base_wr,
            "best_wr": 100 * metrics["win_rate"],
            "pf":      metrics["profit_factor"],
            "seed":    seed,
        })

    # final summary
    print(f"\n{'='*60}")
    print("  FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Combo':<10}  {'Setups':>7}  {'Base':>6}  {'WR':>7}  {'PF':>6}  Seed  Lift")
    print(f"  {'-'*55}")
    for r in summary:
        lift = r["best_wr"] - r["base_wr"]
        print(f"  {r['label']:<10}  {r['setups']:>7,}  "
              f"{r['base_wr']:>5.1f}%  {r['best_wr']:>6.1f}%  "
              f"{r['pf']:>6.2f}  [{r['seed']}]  +{lift:.1f}pp")

    print(f"\nAll weights in: {WEIGHTS_DIR}/")
    print("Done -- you will not need to rerun this.")


if __name__ == "__main__":
    main()

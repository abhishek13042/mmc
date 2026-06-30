"""Train perceptron on ALL available EURUSD data with fixed 2R labels.

Uses the full 100k H1 bar history (2010-2026) instead of the previous 10k limit.
daily_bias_series now runs O(n x 300) instead of O(n^2) so 100k bars is fast.

Run:
    python examples/train_weights_2r.py

Output:
    mmc/brain/weights/EURUSD_H4_H1_2R.json
    mmc/brain/weights/EURUSD_H4_H1_2R.pt
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
TARGET_RR   = 2.0
N_SEEDS     = 5
WEIGHTS_DIR = "D:/MMC/mmc/brain/weights"
CACHE_DIR   = "D:/MMC/mmc/brain/weights/_cache"
LABEL       = "H4_H1_2R"


def get_dataset():
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = f"{CACHE_DIR}/{SYMBOL}_{LABEL}.pkl"
    if os.path.exists(cache):
        print(f"[cache] loading {LABEL}")
        return pickle.load(open(cache, "rb"))
    print(f"[build] {SYMBOL} H4->H1  ALL bars  target_rr={TARGET_RR}")
    ds = build_dataset_v2(
        SYMBOL,
        context_tf=Timeframe.H4,
        entry_tf=Timeframe.H1,
        limit_bars=None,        # use all 100k H1 bars
        target_rr=TARGET_RR,   # fixed 2R TP for every setup
        verbose=True,
    )
    if not ds.empty:
        pickle.dump(ds, open(cache, "wb"))
    return ds


def train_all_seeds(ds):
    cols = FEATURE_NAMES_V2
    d = ds.sort_values("entry_time").reset_index(drop=True)
    tr, vl, te = walk_forward_split(d)

    print(f"\n  Train {len(tr)}  Val {len(vl)}  Test {len(te)}")
    print(f"  Baseline WR: {100*d['label'].mean():.1f}%  (fixed {TARGET_RR}R target)")

    best_wr, best_model, best_metrics, best_seed = -1.0, None, None, 0
    results = []
    for seed in range(N_SEEDS):
        torch.manual_seed(seed)
        np.random.seed(seed)
        m = get_model("perceptron", n_features=len(cols))
        torch.manual_seed(seed)
        train_model_cols(m, tr, vl, cols, epochs=200, patience=25)
        met = evaluate_model_cols(m, te, cols)
        wr, pf = met["win_rate"], met["profit_factor"]
        # real PF uses actual RR, not the eval function's assumed 2R
        tp = met["n_trades"] * wr
        fp = met["n_trades"] * (1 - wr)
        real_pf = (tp * TARGET_RR) / max(fp, 1e-8)
        exp_r   = wr * TARGET_RR - (1 - wr) * 1.0
        results.append((seed, wr, real_pf, exp_r, met))
        print(f"  seed {seed}:  WR={wr:.1%}  real_PF={real_pf:.2f}  "
              f"exp_R={exp_r:+.3f}R  trades={met['n_trades']}/{met['n_total']}")
        if wr > best_wr:
            best_wr, best_model, best_metrics, best_seed = wr, m, met, seed

    return best_model, best_metrics, best_seed, results


def save(model, metrics, seed, ds, all_results):
    os.makedirs(WEIGHTS_DIR, exist_ok=True)
    cols = FEATURE_NAMES_V2
    w = perceptron_weights(model, cols)
    ranked = sorted(w.items(), key=lambda x: abs(x[1]), reverse=True)

    wr = metrics["win_rate"]
    tp = metrics["n_trades"] * wr
    fp = metrics["n_trades"] * (1 - wr)
    real_pf = round((tp * TARGET_RR) / max(fp, 1e-8), 3)
    exp_r   = round(wr * TARGET_RR - (1 - wr) * 1.0, 4)

    seed_summary = [
        {"seed": s, "win_rate": r, "real_pf": round(p,3), "exp_r": round(e,4)}
        for s, r, p, e, _ in all_results
    ]

    payload = {
        "symbol":        SYMBOL,
        "context_tf":    "H4",
        "entry_tf":      "H1",
        "target_rr":     TARGET_RR,
        "trained_date":  datetime.now().strftime("%Y-%m-%d"),
        "limit_bars":    "ALL",
        "n_setups":      len(ds),
        "n_seeds_tried": N_SEEDS,
        "best_seed":     seed,
        "baseline_wr":   round(float(ds["label"].mean()), 4),
        "win_rate":      metrics["win_rate"],
        "real_pf":       real_pf,
        "exp_r_per_trade": exp_r,
        "n_trades":      metrics["n_trades"],
        "n_test":        metrics["n_total"],
        "all_seeds":     seed_summary,
        "feature_names": [k for k, _ in ranked],
        "weights":       [round(v, 6) for _, v in ranked],
        "weight_map":    {k: round(v, 6) for k, v in ranked},
    }

    json_path = f"{WEIGHTS_DIR}/{SYMBOL}_{LABEL}.json"
    pt_path   = f"{WEIGHTS_DIR}/{SYMBOL}_{LABEL}.pt"
    with open(json_path, "w") as f:
        json.dump(payload, f, indent=2)
    torch.save(model.state_dict(), pt_path)
    return json_path, pt_path


def print_weights(w_map, n=20):
    items = sorted(w_map.items(), key=lambda x: abs(x[1]), reverse=True)[:n]
    src = lambda k: "atoz" if k.startswith("az_") else " mmc"
    print(f"\n  {'Feature':<28} {'src':>4}  {'Weight':>8}")
    print(f"  {'-'*45}")
    for feat, wt in items:
        bar  = "#" * min(int(abs(wt) * 10), 20)
        sign = "+" if wt >= 0 else "-"
        print(f"  {feat:<28} {src(feat)}  {sign}{abs(wt):>6.4f}  {bar}")


def main():
    print("=" * 60)
    print(f"  {SYMBOL} H4->H1  ALL DATA  fixed {TARGET_RR}R labels")
    print(f"  {N_SEEDS} seeds  ->  {WEIGHTS_DIR}/{SYMBOL}_{LABEL}.json")
    print("=" * 60)

    ds = get_dataset()
    if ds.empty:
        print("No setups found.")
        return

    base_wr = 100 * ds["label"].mean()
    print(f"\n  {len(ds):,} setups  |  baseline WR {base_wr:.1f}%  (fixed {TARGET_RR}R)")
    print(f"  Training {N_SEEDS} seeds...\n")

    model, metrics, seed, all_results = train_all_seeds(ds)
    json_path, pt_path = save(model, metrics, seed, ds, all_results)
    w_map = perceptron_weights(model, FEATURE_NAMES_V2)

    wr = metrics["win_rate"]
    tp = metrics["n_trades"] * wr
    fp = metrics["n_trades"] * (1 - wr)
    real_pf = (tp * TARGET_RR) / max(fp, 1e-8)
    exp_r   = wr * TARGET_RR - (1 - wr) * 1.0

    print(f"\n{'='*60}")
    print(f"  RESULT  (best seed {seed})")
    print(f"{'='*60}")
    print(f"  Setups (train+val+test): {len(ds):,}")
    print(f"  Test WR:      {100*wr:.1f}%")
    print(f"  Real PF:      {real_pf:.2f}  (actual {TARGET_RR}R reward per win)")
    print(f"  Exp R/trade:  {exp_r:+.3f}R")
    print(f"  Trades taken: {metrics['n_trades']} / {metrics['n_total']} test setups")
    print(f"\n  Saved: {json_path}")
    print(f"         {pt_path}")
    print_weights(w_map)


if __name__ == "__main__":
    main()

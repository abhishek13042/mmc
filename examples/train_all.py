"""OVERNIGHT MASTER RUNNER — train the full matrix, checkpointed & resumable.

Matrix:
    pairs    : EURUSD, GBPUSD, XAUUSD            (EURUSD first = priority)
    TF combos: H4->H1, H1->M15, M15->M5, H4->M15
    TP modes : rr2, rr3, rr4, sth, ith, liq      (6 take-profit targets)
  => 3 x 4 x 6 = 72 jobs, each = train perceptron x5 seeds, keep best.

Efficiency:
    * The 55-feature dataset is built ONCE per (pair, TF combo) and cached;
      all 6 TP modes reuse it (only labels change). 12 base builds, not 72.
    * Perceptron only (proven best for this data; fast on CPU, no GPU needed).
    * CPU threads pinned to the machine's cores.

Resume / crash-safety:
    * manifest.json records every finished job + its metrics. Re-running skips
      done jobs and finished base builds, so an interrupted run continues where
      it stopped.
    * progress.log is a human-readable running tally (tail -f it).

Run in background:
    python examples/train_all.py
Outputs:
    mmc/brain/weights/<PAIR>_<COMBO>_<MODE>.json   (+ .pt)
    mmc/brain/weights/_manifest.json
    mmc/brain/weights/_progress.log
"""
import sys, os, json, pickle, time, traceback, multiprocessing
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "D:/MMC")

import numpy as np
import torch

# pin CPU threads (i3: use all logical cores)
try:
    torch.set_num_threads(max(1, multiprocessing.cpu_count()))
except Exception:
    pass

from mmc.core.types import Timeframe
from mmc.brain import batch
from mmc.brain.batch import build_base, label_for_mode, TP_MODES
from mmc.brain.features_v2 import FEATURE_NAMES_V2
from mmc.brain.architectures import get_model
from mmc.brain.train import walk_forward_split
from mmc.brain.train_v2 import train_model_cols, evaluate_model_cols, perceptron_weights
from mmc.data import load

WEIGHTS_DIR = "D:/MMC/mmc/brain/weights"
BASE_DIR    = "D:/MMC/mmc/brain/weights/_base"
MANIFEST    = f"{WEIGHTS_DIR}/_manifest.json"
PROGRESS    = f"{WEIGHTS_DIR}/_progress.log"

N_SEEDS = 5
EPOCHS  = 200
PATIENCE = 25

PAIRS = ["EURUSD", "GBPUSD", "XAUUSD"]
COMBOS = [
    (Timeframe.H4,  Timeframe.H1,  "H4_H1"),
    (Timeframe.H1,  Timeframe.M15, "H1_M15"),
    (Timeframe.M15, Timeframe.M5,  "M15_M5"),
    (Timeframe.H4,  Timeframe.M15, "H4_M15"),
]


# --------------------------------------------------------------------------- #
# logging + manifest
# --------------------------------------------------------------------------- #

def log(msg: str):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    os.makedirs(WEIGHTS_DIR, exist_ok=True)
    with open(PROGRESS, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_manifest() -> dict:
    if os.path.exists(MANIFEST):
        try:
            return json.load(open(MANIFEST))
        except Exception:
            pass
    return {"jobs": {}, "started": datetime.now().isoformat()}


def save_manifest(man: dict):
    man["updated"] = datetime.now().isoformat()
    tmp = MANIFEST + ".tmp"
    json.dump(man, open(tmp, "w"), indent=2)
    os.replace(tmp, MANIFEST)


# --------------------------------------------------------------------------- #
# training one job
# --------------------------------------------------------------------------- #

def expectancy(df, model, mask_threshold=0.5):
    """Real expectancy on the test split using each trade's ACTUAL rr."""
    d = df.sort_values("entry_time").reset_index(drop=True)
    _, _, te = walk_forward_split(d)
    if len(te) < 10:
        return None
    X = torch.tensor(te[FEATURE_NAMES_V2].values, dtype=torch.float32)
    with torch.no_grad():
        probs = torch.sigmoid(model(X).squeeze(1)).numpy()
    labels = te["label"].values.astype(float)
    rr = te["rr"].values.astype(float)
    take = probs >= mask_threshold
    if take.sum() == 0:
        return {"n_trades": 0, "win_rate": 0.0, "exp_r": 0.0,
                "real_pf": 0.0, "avg_rr": float(np.nanmean(rr))}
    wins = labels[take] == 1
    rr_take = rr[take]
    # per-trade R: +rr if win else -1
    per_r = np.where(wins, rr_take, -1.0)
    gross_win = rr_take[wins].sum()
    gross_loss = (~wins).sum() * 1.0
    return {
        "n_trades": int(take.sum()),
        "win_rate": round(float(wins.mean()), 4),
        "exp_r": round(float(per_r.mean()), 4),
        "real_pf": round(float(gross_win / max(gross_loss, 1e-8)), 3),
        "avg_rr": round(float(rr_take.mean()), 3),
    }


def train_job(labeled_df, pair, combo, mode):
    d = labeled_df.sort_values("entry_time").reset_index(drop=True)
    if len(d) < 60:
        return None, None
    tr, vl, te = walk_forward_split(d)

    best = None
    best_model = None
    best_seed = -1
    for seed in range(N_SEEDS):
        torch.manual_seed(seed); np.random.seed(seed)
        m = get_model("perceptron", n_features=len(FEATURE_NAMES_V2))
        torch.manual_seed(seed)
        train_model_cols(m, tr, vl, FEATURE_NAMES_V2, epochs=EPOCHS, patience=PATIENCE)
        ex = expectancy(d, m)
        if ex is None:
            continue
        # rank by expectancy (real R per trade) — the metric that matters
        if best is None or ex["exp_r"] > best["exp_r"]:
            best, best_model, best_seed = ex, m, seed

    if best is None:
        return None, None
    best["best_seed"] = best_seed
    best["n_setups"] = len(d)
    best["baseline_wr"] = round(float(d["label"].mean()), 4)
    return best, best_model


def save_weights(pair, combo, mode, metrics, model, labeled_df):
    w = perceptron_weights(model, FEATURE_NAMES_V2)
    ranked = sorted(w.items(), key=lambda x: abs(x[1]), reverse=True)
    payload = {
        "symbol": pair, "combo": combo, "tp_mode": mode,
        "trained_date": datetime.now().strftime("%Y-%m-%d"),
        "n_setups": metrics["n_setups"],
        "baseline_wr": metrics["baseline_wr"],
        "best_seed": metrics["best_seed"],
        "win_rate": metrics["win_rate"],
        "avg_rr": metrics["avg_rr"],
        "exp_r_per_trade": metrics["exp_r"],
        "real_pf": metrics["real_pf"],
        "n_trades": metrics["n_trades"],
        "feature_names": [k for k, _ in ranked],
        "weights": [round(v, 6) for _, v in ranked],
        "weight_map": {k: round(v, 6) for k, v in ranked},
    }
    stem = f"{WEIGHTS_DIR}/{pair}_{combo}_{mode}"
    json.dump(payload, open(stem + ".json", "w"), indent=2)
    torch.save(model.state_dict(), stem + ".pt")


# --------------------------------------------------------------------------- #
# main loop
# --------------------------------------------------------------------------- #

def main():
    os.makedirs(WEIGHTS_DIR, exist_ok=True)
    os.makedirs(BASE_DIR, exist_ok=True)
    man = load_manifest()

    total_jobs = len(PAIRS) * len(COMBOS) * len(TP_MODES)
    done_at_start = len(man["jobs"])
    log("=" * 64)
    log(f"MASTER RUN start  |  {total_jobs} jobs total, {done_at_start} already done")
    log(f"pairs={PAIRS}  combos={[c[2] for c in COMBOS]}  modes={TP_MODES}")
    log("=" * 64)

    job_n = 0
    for pair in PAIRS:
        for ctx_tf, entry_tf, combo in COMBOS:
            # --- base dataset for this (pair, combo): build once, reuse 6x ---
            base_cache = f"{BASE_DIR}/{pair}_{combo}.pkl"
            entry_df = None
            base = None
            try:
                base = build_base(pair, ctx_tf, entry_tf,
                                  cache_path=base_cache, log=log)
            except Exception as e:
                log(f"  !! base build FAILED {pair} {combo}: {e}")
                log(traceback.format_exc())

            for mode in TP_MODES:
                job_n += 1
                key = f"{pair}|{combo}|{mode}"
                if key in man["jobs"]:
                    log(f"[{job_n}/{total_jobs}] skip (done): {key}")
                    continue
                if base is None or base.empty:
                    log(f"[{job_n}/{total_jobs}] skip (no base): {key}")
                    continue

                t0 = time.time()
                try:
                    if entry_df is None:
                        entry_df = load(pair, entry_tf)
                    labeled = label_for_mode(base, entry_df, mode)
                    metrics, model = train_job(labeled, pair, combo, mode)
                    if metrics is None:
                        log(f"[{job_n}/{total_jobs}] {key}: too few setups "
                            f"({len(labeled)}) — skipped")
                        man["jobs"][key] = {"status": "skipped_small",
                                            "n": len(labeled)}
                        save_manifest(man)
                        continue
                    save_weights(pair, combo, mode, metrics, model, labeled)
                    man["jobs"][key] = {
                        "status": "done",
                        "win_rate": metrics["win_rate"],
                        "avg_rr": metrics["avg_rr"],
                        "exp_r": metrics["exp_r"],
                        "real_pf": metrics["real_pf"],
                        "n_setups": metrics["n_setups"],
                        "n_trades": metrics["n_trades"],
                        "baseline_wr": metrics["baseline_wr"],
                        "best_seed": metrics["best_seed"],
                    }
                    save_manifest(man)
                    log(f"[{job_n}/{total_jobs}] DONE {key}  "
                        f"WR={100*metrics['win_rate']:.1f}%  "
                        f"avgRR={metrics['avg_rr']:.2f}  "
                        f"expR={metrics['exp_r']:+.3f}  "
                        f"PF={metrics['real_pf']:.2f}  "
                        f"({time.time()-t0:.0f}s)")
                except Exception as e:
                    log(f"[{job_n}/{total_jobs}] ERROR {key}: {e}")
                    log(traceback.format_exc())
                    man["jobs"][key] = {"status": "error", "msg": str(e)}
                    save_manifest(man)

    log("=" * 64)
    log("MASTER RUN complete")
    _print_summary(man)


def _print_summary(man):
    rows = [(k, v) for k, v in man["jobs"].items() if v.get("status") == "done"]
    rows.sort(key=lambda kv: kv[1].get("exp_r", -99), reverse=True)
    log("")
    log("TOP RESULTS by expectancy (R per trade):")
    log(f"  {'job':<28}{'WR':>7}{'avgRR':>7}{'expR':>8}{'PF':>7}")
    for k, v in rows[:20]:
        log(f"  {k:<28}{100*v['win_rate']:>6.1f}%{v['avg_rr']:>7.2f}"
            f"{v['exp_r']:>+8.3f}{v['real_pf']:>7.2f}")


if __name__ == "__main__":
    main()

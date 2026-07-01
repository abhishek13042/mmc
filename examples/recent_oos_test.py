"""Realistic out-of-sample test — most recent 2 months, traded like the robot.

Unlike a naive per-setup tally, this enforces what a real account faces:
  * ONE position per symbol at a time — setups that fire while a trade is open
    are skipped (you were already busy), so overlapping trades don't double-count.
  * SPREAD cost charged on every trade (entry spread / risk, in R).
  * Sequential event simulation: each taken trade is walked forward bar-by-bar to
    its real exit (TP or SL, wick-aware, loss on a tie) to find when you're free
    again.

These bars are in the held-out tail (model trained on the earlier 70%), so it is
a genuine out-of-sample read of the last two months.
"""
import sys, os, pickle, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "D:/MMC")

import numpy as np
import pandas as pd
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mmc.data import load
from mmc.core.types import Timeframe
from mmc.core import Direction, find_fvgs, mark_mitigation
from mmc.brain.features_v2 import FEATURE_NAMES_V2
from mmc.brain.architectures import get_model

WEIGHTS = "D:/MMC/mmc/brain/weights"
BASE    = f"{WEIGHTS}/_base"
OUT_PNG = f"{WEIGHTS}/charts/recent_oos_equity.png"

MONTHS    = 2
THRESHOLD = 0.50
TARGET_RR = 4.0
MAX_BARS  = 200

# pair -> (combo label, entry timeframe, realistic spread in PRICE)
CONFIGS = {
    "EURUSD": ("H4_M15", Timeframe.M15, 0.00008),   # ~0.8 pip
    "GBPUSD": ("H4_M15", Timeframe.M15, 0.00012),   # ~1.2 pip
    "XAUUSD": ("M15_M5", Timeframe.M5,  0.20),      # ~20 cents
}


def run_pair(pair, combo, entry_tf, spread):
    base = pickle.load(open(f"{BASE}/{pair}_{combo}.pkl", "rb"))
    entry_df = load(pair, entry_tf)
    highs = entry_df["high"].to_numpy()
    lows  = entry_df["low"].to_numpy()
    n = len(entry_df)

    # score every setup with the trained model
    model = get_model("perceptron", n_features=len(FEATURE_NAMES_V2))
    model.load_state_dict(torch.load(f"{WEIGHTS}/{pair}_{combo}_rr4.pt", map_location="cpu"))
    model.eval()
    X = torch.tensor(base[FEATURE_NAMES_V2].values, dtype=torch.float32)
    with torch.no_grad():
        base = base.copy()
        base["score"] = torch.sigmoid(model(X).squeeze(1)).numpy()

    # most recent MONTHS window
    base = base.sort_values("entry_time").reset_index(drop=True)
    cutoff = base["entry_time"].max() - pd.Timedelta(days=30 * MONTHS)
    recent = base[base["entry_time"] >= cutoff].reset_index(drop=True)

    # sequential, one-position-at-a-time simulation
    trades = []
    free_bar = -1
    for _, r in recent.iterrows():
        if r["score"] < THRESHOLD:
            continue
        b = int(r["entry_bar"])
        if b <= free_bar:                     # still in a trade -> skip
            continue
        entry = r["entry_price"]; stop = r["stop"]; risk = r["risk"]
        bullish = r["dir_sign"] > 0
        tp = entry + TARGET_RR * risk if bullish else entry - TARGET_RR * risk

        # walk forward to the real exit
        outcome, exit_bar = None, min(n - 1, b + MAX_BARS)
        for j in range(b + 1, min(n, b + MAX_BARS + 1)):
            if bullish:
                sl_hit = lows[j] <= stop
                tp_hit = highs[j] >= tp
            else:
                sl_hit = highs[j] >= stop
                tp_hit = lows[j] <= tp
            if sl_hit and tp_hit:
                outcome, exit_bar = "loss", j; break      # tie -> loss (conservative)
            if tp_hit:
                outcome, exit_bar = "win", j; break
            if sl_hit:
                outcome, exit_bar = "loss", j; break
        if outcome is None:
            continue                          # unresolved -> skip

        gross = TARGET_RR if outcome == "win" else -1.0
        cost_R = spread / risk                # entry spread in R
        net = gross - cost_R
        trades.append({"time": r["entry_time"], "R": net, "win": outcome == "win"})
        free_bar = exit_bar

    tdf = pd.DataFrame(trades)
    if tdf.empty:
        return {"pair": pair, "trades": 0, "curve": tdf}
    tdf["equity"] = tdf["R"].cumsum()
    nt = len(tdf); wins = int(tdf["win"].sum())
    wr = wins / nt
    gw = tdf.loc[tdf["R"] > 0, "R"].sum()
    gl = -tdf.loc[tdf["R"] <= 0, "R"].sum()
    pf = gw / gl if gl else float("inf")
    eq = tdf["equity"].values
    dd = (eq - np.maximum.accumulate(eq)).min()
    return {
        "pair": pair, "window": f"{cutoff.date()} -> {recent['entry_time'].max().date()}",
        "trades": nt, "wins": wins, "win_rate": wr, "pf": pf,
        "exp_r": tdf["R"].mean(), "total_r": tdf["R"].sum(), "max_dd": dd,
        "curve": tdf,
    }


def main():
    os.makedirs(f"{WEIGHTS}/charts", exist_ok=True)
    print("=" * 78)
    print(f"  REALISTIC OUT-OF-SAMPLE — last {MONTHS} months | 4R | score>={THRESHOLD} "
          f"| 1 pos/symbol | spread charged")
    print("=" * 78)
    print(f"  {'pair':<8}{'window':<26}{'trades':>7}{'WR':>7}{'PF':>7}{'expR':>8}{'totR':>8}{'maxDD':>8}")
    print("  " + "-" * 74)

    results = []
    for pair, (combo, tf, spread) in CONFIGS.items():
        r = run_pair(pair, combo, tf, spread)
        results.append(r)
        if r["trades"] == 0:
            print(f"  {pair:<8}no trades"); continue
        print(f"  {r['pair']:<8}{r['window']:<26}{r['trades']:>7}"
              f"{100*r['win_rate']:>6.1f}%{r['pf']:>7.2f}{r['exp_r']:>+8.3f}"
              f"{r['total_r']:>+8.1f}{r['max_dd']:>+8.1f}")

    print("  " + "-" * 74)
    tt = sum(r["trades"] for r in results)
    tw = sum(r.get("wins", 0) for r in results)
    tr = sum(r.get("total_r", 0) for r in results)
    gw = sum(r["curve"].loc[r["curve"]["R"] > 0, "R"].sum() for r in results if r["trades"])
    gl = sum(-r["curve"].loc[r["curve"]["R"] <= 0, "R"].sum() for r in results if r["trades"])
    print(f"  {'ALL':<8}{'combined':<26}{tt:>7}{100*tw/max(tt,1):>6.1f}%"
          f"{gw/max(gl,1e-9):>7.2f}{tr/max(tt,1):>+8.3f}{tr:>+8.1f}")
    print()
    print(f"  At 1% risk per trade, +{tr:.0f}R over {MONTHS} months ~ {tr:.0%} account growth")
    print(f"  (simple, non-compounded) from {tt} trades.  This is spread-adjusted and")
    print(f"  one-position-at-a-time — far more realistic than a raw per-setup tally.")

    # equity curves
    fig, ax = plt.subplots(figsize=(11, 6))
    for r in results:
        if r["trades"]:
            c = r["curve"]
            ax.plot(c["time"], c["equity"], marker="o", ms=2,
                    label=f"{r['pair']} — {r['trades']}t, {100*r['win_rate']:.0f}% WR, "
                          f"PF {r['pf']:.2f}, {r['total_r']:+.0f}R")
    ax.axhline(0, color="k", lw=0.8)
    ax.set_ylabel("cumulative R (risk units)")
    ax.set_xlabel("trade time")
    ax.set_title(f"Realistic out-of-sample equity — last {MONTHS} months "
                 f"(1 pos/symbol, spread-adjusted, 4R)", fontweight="bold")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=130, bbox_inches="tight")
    print(f"\n  equity curve -> {OUT_PNG}")


if __name__ == "__main__":
    main()

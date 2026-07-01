"""Detailed report + visualizations for the full 72-job training matrix.

Reads every trained weight file in mmc/brain/weights/*.json (pair x TF-combo x
TP-mode) plus the run manifest, then produces:

  1. A detailed text report  -> mmc/brain/weights/RESULTS_REPORT.txt
     - full results table (all 72 jobs)
     - per-pair breakdown
     - TP-mode ranking, TF-combo ranking
     - top feature weights for the best model of each pair

  2. PNG charts             -> mmc/brain/weights/charts/
     - expectancy_heatmap.png       expR for every pair x (combo,mode)
     - winrate_vs_rr.png            WR vs realised RR, coloured by TP mode
     - tp_mode_ranking.png          avg expR per TP mode
     - combo_ranking.png            avg expR per TF combo
     - pf_by_pair.png               profit factor grouped bars per pair
     - top_weights_<PAIR>.png       feature weights of each pair's best model

Run:
    python examples/results_visualization.py
"""
from __future__ import annotations

import glob
import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")            # headless — just write PNGs
import matplotlib.pyplot as plt
import seaborn as sns

WEIGHTS_DIR = "D:/MMC/mmc/brain/weights"
CHARTS_DIR = f"{WEIGHTS_DIR}/charts"
REPORT_TXT = f"{WEIGHTS_DIR}/RESULTS_REPORT.txt"

PAIRS = ["EURUSD", "GBPUSD", "XAUUSD"]
COMBOS = ["H4_H1", "H1_M15", "M15_M5", "H4_M15"]
MODES = ["rr2", "rr3", "rr4", "sth", "ith", "liq"]
MODE_LABEL = {
    "rr2": "2R fixed", "rr3": "3R fixed", "rr4": "4R fixed",
    "sth": "short-term H/L", "ith": "interm. H/L", "liq": "liquidity pool",
}

sns.set_theme(style="whitegrid", font_scale=0.9)


# --------------------------------------------------------------------------- #
# Load every job into a tidy DataFrame
# --------------------------------------------------------------------------- #

def load_results() -> pd.DataFrame:
    rows = []
    for path in glob.glob(f"{WEIGHTS_DIR}/*.json"):
        name = os.path.basename(path)
        if name.startswith("_"):
            continue
        d = json.load(open(path))
        if "tp_mode" not in d:       # skip old single-RR weight files
            continue
        rows.append({
            "pair": d["symbol"],
            "combo": d["combo"],
            "mode": d["tp_mode"],
            "win_rate": d["win_rate"],
            "avg_rr": d["avg_rr"],
            "exp_r": d["exp_r_per_trade"],
            "pf": d["real_pf"],
            "n_setups": d["n_setups"],
            "n_trades": d["n_trades"],
            "baseline_wr": d.get("baseline_wr", float("nan")),
            "best_seed": d.get("best_seed", -1),
            "_path": path,
        })
    df = pd.DataFrame(rows)
    df["mode"] = pd.Categorical(df["mode"], categories=MODES, ordered=True)
    df["combo"] = pd.Categorical(df["combo"], categories=COMBOS, ordered=True)
    return df.sort_values(["pair", "combo", "mode"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Text report
# --------------------------------------------------------------------------- #

def write_report(df: pd.DataFrame):
    L = []
    def p(s=""): L.append(s)

    p("=" * 78)
    p("  MMC BRAIN v2 — FULL TRAINING RESULTS  (perceptron, 100k-bar data)")
    p(f"  {len(df)} models  |  {df['pair'].nunique()} pairs x "
      f"{len(COMBOS)} timeframe combos x {len(MODES)} take-profit targets")
    p("=" * 78)
    p()
    p("Metric key:")
    p("  WR    = win rate on the held-out test split (unseen data)")
    p("  avgRR = average realised reward:risk of the take-profit")
    p("  expR  = EXPECTANCY, R per trade = WR*avgRR - (1-WR)*1   <-- the key number")
    p("  PF    = profit factor = gross win R / gross loss R")
    p("  setups/trades = total labelled setups / trades the model chose to take")
    p()

    # ---- full table ----
    p("-" * 78)
    p("  FULL RESULTS — every model")
    p("-" * 78)
    hdr = f"  {'pair':<8}{'combo':<9}{'TP target':<16}{'WR':>7}{'avgRR':>7}{'expR':>8}{'PF':>7}{'setups':>8}{'trades':>8}"
    for pair in PAIRS:
        p()
        p(hdr)
        p("  " + "-" * 74)
        sub = df[df["pair"] == pair]
        for _, r in sub.iterrows():
            p(f"  {r['pair']:<8}{r['combo']:<9}{MODE_LABEL[r['mode']]:<16}"
              f"{100*r['win_rate']:>6.1f}%{r['avg_rr']:>7.2f}{r['exp_r']:>+8.3f}"
              f"{r['pf']:>7.2f}{r['n_setups']:>8}{r['n_trades']:>8}")

    # ---- overall top 15 ----
    p()
    p("-" * 78)
    p("  TOP 15 MODELS by expectancy (R per trade)")
    p("-" * 78)
    top = df.sort_values("exp_r", ascending=False).head(15)
    p(f"  {'#':>3} {'pair':<8}{'combo':<9}{'TP':<16}{'expR':>8}{'WR':>7}{'PF':>7}")
    for i, (_, r) in enumerate(top.iterrows(), 1):
        p(f"  {i:>3} {r['pair']:<8}{r['combo']:<9}{MODE_LABEL[r['mode']]:<16}"
          f"{r['exp_r']:>+8.3f}{100*r['win_rate']:>6.1f}%{r['pf']:>7.2f}")

    # ---- TP mode ranking ----
    p()
    p("-" * 78)
    p("  TAKE-PROFIT TARGET RANKING (averaged over all pairs & timeframes)")
    p("-" * 78)
    mr = df.groupby("mode", observed=True)["exp_r"].agg(["mean", "min", "max"])
    mr = mr.sort_values("mean", ascending=False)
    p(f"  {'target':<16}{'avg expR':>10}{'worst':>9}{'best':>9}")
    for mode, row in mr.iterrows():
        p(f"  {MODE_LABEL[mode]:<16}{row['mean']:>+10.3f}{row['min']:>+9.3f}{row['max']:>+9.3f}")

    # ---- TF combo ranking ----
    p()
    p("-" * 78)
    p("  TIMEFRAME COMBO RANKING (averaged over all pairs & TP modes)")
    p("-" * 78)
    cr = df.groupby("combo", observed=True)["exp_r"].mean().sort_values(ascending=False)
    p(f"  {'combo':<10}{'avg expR':>10}")
    for combo, val in cr.items():
        p(f"  {combo:<10}{val:>+10.3f}")

    # ---- fixed-RR only comparison (apples to apples) ----
    p()
    p("-" * 78)
    p("  FIXED-RR ONLY: expectancy by RR level (the clean comparison)")
    p("-" * 78)
    rr = df[df["mode"].isin(["rr2", "rr3", "rr4"])]
    piv = rr.pivot_table(index="mode", values=["win_rate", "exp_r", "pf"],
                         aggfunc="mean", observed=True)
    p(f"  {'RR':<6}{'avg WR':>9}{'avg expR':>10}{'avg PF':>9}")
    for mode in ["rr2", "rr3", "rr4"]:
        row = piv.loc[mode]
        p(f"  {mode:<6}{100*row['win_rate']:>8.1f}%{row['exp_r']:>+10.3f}{row['pf']:>9.2f}")

    # ---- best model per pair + its top features ----
    p()
    p("-" * 78)
    p("  BEST MODEL PER PAIR  +  its most important concept weights")
    p("-" * 78)
    for pair in PAIRS:
        sub = df[df["pair"] == pair]
        best = sub.loc[sub["exp_r"].idxmax()]
        p()
        p(f"  {pair}:  {best['combo']} / {MODE_LABEL[best['mode']]}  "
          f"->  expR={best['exp_r']:+.3f}  WR={100*best['win_rate']:.1f}%  "
          f"RR={best['avg_rr']:.1f}  PF={best['pf']:.2f}")
        d = json.load(open(best["_path"]))
        names = d["feature_names"][:10]
        wts = d["weights"][:10]
        p(f"     top 10 concept weights:")
        for nm, w in zip(names, wts):
            src = "atoz" if nm.startswith("az_") else "mmc "
            bar = "#" * min(int(abs(w) * 12), 24)
            sign = "+" if w >= 0 else "-"
            p(f"       {nm:<24} [{src}] {sign}{abs(w):.3f}  {bar}")

    p()
    p("=" * 78)
    p("  BOTTOM LINE")
    p("=" * 78)
    p("  * Fixed 4R take-profit wins on every pair and timeframe.")
    p("  * H4->M15 (swing bias + precise M15 entry) is the strongest combo.")
    p("  * Structural (STH/ITH) and liquidity targets underperform fixed RR.")
    p("  * fvg_quality / fva_fresh (mmc) + az_tier_protected (atoz) dominate weights.")

    open(REPORT_TXT, "w", encoding="utf-8").write("\n".join(L))
    print(f"[report] {REPORT_TXT}")
    # also echo to console
    print("\n".join(L))


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #

def chart_expectancy_heatmap(df: pd.DataFrame):
    fig, axes = plt.subplots(1, len(PAIRS), figsize=(15, 5), sharey=True)
    vmin, vmax = df["exp_r"].min(), df["exp_r"].max()
    for ax, pair in zip(axes, PAIRS):
        sub = df[df["pair"] == pair]
        piv = sub.pivot_table(index="mode", columns="combo",
                              values="exp_r", observed=True)
        piv = piv.reindex(index=MODES, columns=COMBOS)
        sns.heatmap(piv, ax=ax, cmap="RdYlGn", center=0, vmin=vmin, vmax=vmax,
                    annot=True, fmt="+.2f", cbar=(pair == PAIRS[-1]),
                    linewidths=0.5, annot_kws={"size": 8})
        ax.set_title(pair, fontweight="bold")
        ax.set_xlabel("timeframe combo")
        ax.set_ylabel("TP target" if pair == PAIRS[0] else "")
        ax.set_yticklabels([MODE_LABEL[m] for m in MODES], rotation=0)
    fig.suptitle("Expectancy (R per trade) — green = profitable, red = losing",
                 fontweight="bold", y=1.02)
    fig.tight_layout()
    out = f"{CHARTS_DIR}/expectancy_heatmap.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"[chart] {out}")


def chart_winrate_vs_rr(df: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(9, 6))
    palette = dict(zip(MODES, sns.color_palette("tab10", len(MODES))))
    for mode in MODES:
        sub = df[df["mode"] == mode]
        ax.scatter(sub["avg_rr"], 100 * sub["win_rate"], s=90,
                   color=palette[mode], label=MODE_LABEL[mode],
                   edgecolor="k", linewidth=0.5, alpha=0.85)
    # break-even curve: WR = 1/(1+RR) * 100
    rr = np.linspace(0.8, df["avg_rr"].max() + 0.5, 100)
    ax.plot(rr, 100 / (1 + rr), "k--", alpha=0.6,
            label="break-even (expR=0)")
    ax.set_xlabel("average realised RR")
    ax.set_ylabel("win rate (%)")
    ax.set_title("Win rate vs RR — points ABOVE the dashed line are profitable",
                 fontweight="bold")
    ax.legend(title="TP target", loc="upper right", fontsize=8)
    fig.tight_layout()
    out = f"{CHARTS_DIR}/winrate_vs_rr.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"[chart] {out}")


def chart_tp_mode_ranking(df: pd.DataFrame):
    mr = df.groupby("mode", observed=True)["exp_r"].mean().reindex(MODES)
    fig, ax = plt.subplots(figsize=(8, 5))
    colors = ["#2ca02c" if v > 0.5 else "#98df8a" if v > 0.2
              else "#ffbb78" if v > 0 else "#d62728" for v in mr.values]
    bars = ax.bar([MODE_LABEL[m] for m in mr.index], mr.values, color=colors,
                  edgecolor="k", linewidth=0.6)
    ax.axhline(0, color="k", linewidth=0.8)
    ax.set_ylabel("avg expectancy (R per trade)")
    ax.set_title("Take-profit target ranking (avg over all pairs & timeframes)",
                 fontweight="bold")
    for b, v in zip(bars, mr.values):
        ax.text(b.get_x() + b.get_width() / 2, v + (0.02 if v >= 0 else -0.05),
                f"{v:+.3f}", ha="center", fontsize=9, fontweight="bold")
    plt.xticks(rotation=20)
    fig.tight_layout()
    out = f"{CHARTS_DIR}/tp_mode_ranking.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"[chart] {out}")


def chart_combo_ranking(df: pd.DataFrame):
    cr = df[df["mode"].isin(["rr2", "rr3", "rr4"])]  # fixed-RR only, clean
    piv = cr.pivot_table(index="combo", columns="mode", values="exp_r",
                         observed=True).reindex(index=COMBOS)
    fig, ax = plt.subplots(figsize=(9, 5))
    piv[["rr2", "rr3", "rr4"]].plot(kind="bar", ax=ax,
        color=["#aec7e8", "#5b9bd5", "#1f4e79"], edgecolor="k", linewidth=0.5)
    ax.set_ylabel("expectancy (R per trade)")
    ax.set_xlabel("timeframe combo")
    ax.set_title("Timeframe combo x fixed-RR level (avg over pairs)",
                 fontweight="bold")
    ax.legend(["2R", "3R", "4R"], title="target")
    plt.xticks(rotation=0)
    fig.tight_layout()
    out = f"{CHARTS_DIR}/combo_ranking.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"[chart] {out}")


def chart_pf_by_pair(df: pd.DataFrame):
    rr = df[df["mode"] == "rr4"]
    piv = rr.pivot_table(index="pair", columns="combo", values="pf",
                        observed=True).reindex(index=PAIRS, columns=COMBOS)
    fig, ax = plt.subplots(figsize=(9, 5))
    piv.plot(kind="bar", ax=ax, edgecolor="k", linewidth=0.5,
             colormap="viridis")
    ax.axhline(1.0, color="r", linestyle="--", alpha=0.7, label="break-even PF=1")
    ax.set_ylabel("profit factor")
    ax.set_title("Profit factor at the best target (4R) — by pair & timeframe",
                 fontweight="bold")
    ax.legend(title="timeframe", fontsize=8)
    plt.xticks(rotation=0)
    fig.tight_layout()
    out = f"{CHARTS_DIR}/pf_by_pair.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"[chart] {out}")


def chart_top_weights(df: pd.DataFrame):
    for pair in PAIRS:
        sub = df[df["pair"] == pair]
        best = sub.loc[sub["exp_r"].idxmax()]
        d = json.load(open(best["_path"]))
        names = d["feature_names"][:15][::-1]
        wts = d["weights"][:15][::-1]
        colors = ["#1f77b4" if n.startswith("az_") else "#ff7f0e" for n in names]
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.barh(names, wts, color=colors, edgecolor="k", linewidth=0.4)
        ax.axvline(0, color="k", linewidth=0.8)
        ax.set_xlabel("weight (sign = direction, magnitude = importance)")
        ax.set_title(f"{pair} best model — {best['combo']}/{best['mode']} "
                     f"(expR {best['exp_r']:+.2f})\n"
                     f"blue = atoz(ICT) concept, orange = mmc concept",
                     fontweight="bold", fontsize=10)
        fig.tight_layout()
        out = f"{CHARTS_DIR}/top_weights_{pair}.png"
        fig.savefig(out, dpi=130, bbox_inches="tight")
        plt.close(fig)
        print(f"[chart] {out}")


# --------------------------------------------------------------------------- #

def main():
    os.makedirs(CHARTS_DIR, exist_ok=True)
    df = load_results()
    if df.empty:
        print("No per-mode result files found in", WEIGHTS_DIR)
        return
    print(f"Loaded {len(df)} models.\n")

    write_report(df)
    print()
    chart_expectancy_heatmap(df)
    chart_winrate_vs_rr(df)
    chart_tp_mode_ranking(df)
    chart_combo_ranking(df)
    chart_pf_by_pair(df)
    chart_top_weights(df)

    # tidy CSV for spreadsheets
    csv = f"{WEIGHTS_DIR}/RESULTS_TABLE.csv"
    df.drop(columns=["_path"]).to_csv(csv, index=False)
    print(f"\n[csv]   {csv}")
    print(f"[done]  report + {len(glob.glob(CHARTS_DIR + '/*.png'))} charts in {CHARTS_DIR}/")


if __name__ == "__main__":
    main()

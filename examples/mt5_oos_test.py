"""OUT-OF-SAMPLE test on FRESH MT5 candles — last 2 months, all TOP-15 setups.

Unlike recent_oos_test.py (which reads the stored 100k dataset), this pulls the
candles LIVE from the running MetaTrader 5 terminal, so it reflects exactly what
your broker's feed looks like right now.

For each of the 15 fleet strategies it:
  * pulls entry-TF + HTF (+ SMT correlated) candles straight from MT5,
  * rebuilds the 55-feature setups with the SAME code as the backtest
    (mmc.brain.batch.build_base internals -> byte parity),
  * scores every mitigated FVG with that strategy's trained perceptron,
  * keeps only setups in the last 2 months (widen with --months),
  * simulates ONE-position-at-a-time, FIXED 0.20-pip spread charged (--spread-pips),
    wick-aware exit,
  * reports WR / PF / expectancy / total-R per strategy and combined,
  * exports a rich per-trade CSV for the mmc.evaluation pipeline.

Pulling candle data is READ-ONLY — no orders are placed.

RUN:  python examples/mt5_oos_test.py [--months 12] [--all72] [--spread-pips 0.20]
"""
from __future__ import annotations

import sys, os, warnings, json, pickle, time
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
warnings.filterwarnings("ignore")
sys.path.insert(0, "D:/MMC")

import numpy as np
import pandas as pd
import torch

try:
    import MetaTrader5 as mt5
except ImportError:
    raise SystemExit("MetaTrader5 not installed.  pip install MetaTrader5")

from mmc.core import Direction, find_fvgs, mark_mitigation
from mmc.core.types import Timeframe
from mmc.brain.features_v2 import FEATURE_NAMES_V2, extract_features_v2
from mmc.brain.atoz_features import AtozSignals
from mmc.brain.architectures import get_model
from mmc.brain.batch import (
    _atr_series, _structural_targets, _nearest_target,
    CONTEXT_LOOKBACK, MAX_FWD_BARS,
)
from mmc.brain.labels import label_trade
from mmc.evaluation.progress import Status, Tee

WEIGHTS = "D:/MMC/mmc/brain/weights"
MONTHS    = 2
THRESHOLD = 0.50
MAX_BARS  = MAX_FWD_BARS
# FIXED spread charged on every entry, in pips (pip = 10 x the symbol's point,
# so 0.20 pips is ~0.00002 on EUR/GBP and ~0.02 on XAU). Replaces the live
# broker snapshot -> reproducible, not tied to whatever the feed showed at run.
SPREAD_PIPS = 0.20

# approximate bars per calendar day per timeframe (24h markets). Used to size
# the pull to the requested window instead of a blind multiplier — a 12-month
# H4 window is ~2k bars, NOT 36k, so we never over-request beyond what the
# terminal actually has (that returns "Call failed").
_BARS_PER_DAY = {Timeframe.M5: 288, Timeframe.M15: 96,
                 Timeframe.H1: 24, Timeframe.H4: 6}
_WARMUP_BARS = 3000          # extra bars before the window for indicators/atoz/structure
PULL_FLOOR = 1200            # never request fewer than this (need warmup regardless)
PULL = {Timeframe.M5: None, Timeframe.M15: None,
        Timeframe.H1: None, Timeframe.H4: None}   # kept only for the TF key set
_MT5_TF = {Timeframe.M5: mt5.TIMEFRAME_M5, Timeframe.M15: mt5.TIMEFRAME_M15,
           Timeframe.H1: mt5.TIMEFRAME_H1, Timeframe.H4: mt5.TIMEFRAME_H4}
_CORR = {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD", "XAUUSD": None}


def _needed_bars(tf: Timeframe, months: int) -> int:
    """Bars needed to cover `months` of history + warmup for a timeframe.
    ~30 days/month, 1.4x cushion for weekend gaps."""
    window = int(months * 30 * _BARS_PER_DAY.get(tf, 24) * 1.4)
    return max(PULL_FLOOR, window + _WARMUP_BARS)

# TOP 15 by expectancy (pair, "<HTF>_<ENTRY>", rr) — same list the fleet trades
TOP15 = [
    ("GBPUSD", "H4_M15", 4), ("GBPUSD", "H4_H1", 4), ("GBPUSD", "H1_M15", 4),
    ("XAUUSD", "M15_M5", 4), ("EURUSD", "H4_M15", 4), ("EURUSD", "H4_H1", 4),
    ("EURUSD", "M15_M5", 4), ("EURUSD", "H1_M15", 4), ("XAUUSD", "H1_M15", 4),
    ("XAUUSD", "H4_H1", 4),  ("GBPUSD", "M15_M5", 4), ("XAUUSD", "H4_M15", 4),
    ("XAUUSD", "M15_M5", 3), ("GBPUSD", "H4_H1", 3),  ("EURUSD", "H4_H1", 3),
]

_TF = {"M5": Timeframe.M5, "M15": Timeframe.M15, "H1": Timeframe.H1, "H4": Timeframe.H4}


def get_bars(symbol: str, tf: Timeframe, n: int, retries: int = 3) -> pd.DataFrame:
    """Last ~n CLOSED bars from MT5 as an mmc-format DataFrame.

    Resilient: retries transient 'Call failed' errors, and if the terminal
    can't serve ``n`` bars it backs off (halves the request) down to
    ``PULL_FLOOR`` rather than crashing the whole run — you just get whatever
    history exists (the date-based window filter downstream handles a shorter
    span). Raises only if even the floor request returns nothing usable.
    """
    mt5.symbol_select(symbol, True)
    req = int(n)
    last_err = None
    while req >= PULL_FLOOR:
        for _ in range(retries):
            rates = mt5.copy_rates_from_pos(symbol, _MT5_TF[tf], 0, req + 1)
            if rates is not None and len(rates) >= 100:
                df = pd.DataFrame(rates)
                df["datetime"] = pd.to_datetime(df["time"], unit="s")
                df = df.set_index("datetime").rename(columns={"tick_volume": "volume"})
                df = df[["open", "high", "low", "close", "volume"]].astype(float)
                return df.iloc[:-1]           # drop the still-forming bar
            last_err = mt5.last_error()
            time.sleep(0.5)                    # transient — let the terminal catch up
        req //= 2                              # over-asked — request fewer and retry
    raise RuntimeError(f"No/insufficient rates for {symbol} {tf.name} "
                       f"(backed off to {req * 2}): {last_err}")


def build_base_from_df(symbol, entry_df, htf_df, corr_df) -> pd.DataFrame:
    """Mirror of batch.build_base but on in-memory MT5 candles (same math)."""
    n = len(entry_df)
    atoz_signals = AtozSignals.precompute(entry_df, htf_df=htf_df)
    fvgs = find_fvgs(entry_df)
    mark_mitigation(entry_df, fvgs)
    atr = _atr_series(entry_df)
    targets = _structural_targets(entry_df)

    rows = []
    for fvg in fvgs:
        bar = getattr(fvg, "mitigation_index", None)
        if bar is None or not getattr(fvg, "mitigated", False):
            continue
        if bar < CONTEXT_LOOKBACK or bar >= n - MAX_FWD_BARS:
            continue
        buf = atr[bar] * 0.1 if atr[bar] > 0 else 0.0
        bullish = fvg.direction is Direction.BULLISH
        if bullish:
            entry = fvg.top; stop = fvg.bottom - buf; risk = entry - stop
        else:
            entry = fvg.bottom; stop = fvg.top + buf; risk = stop - entry
        if risk <= 0:
            continue
        feats = extract_features_v2(bar, entry_df, atoz_signals,
                                    htf_df=htf_df, corr_df=corr_df, direction=fvg.direction)
        row = {k: float(feats[i]) for i, k in enumerate(FEATURE_NAMES_V2)}
        row.update({"entry_bar": bar, "entry_time": entry_df.index[bar],
                    "dir_sign": 1 if bullish else -1,
                    "entry_price": float(entry), "stop": float(stop), "risk": float(risk)})
        rows.append(row)
    return pd.DataFrame(rows).reset_index(drop=True)


def _build_base_task(args):
    """Top-level (picklable) worker for the base-building process pool: a pure
    CPU feature build on already-pulled candles. Does NOT touch MT5, so many can
    run in parallel safely. Returns ((pair, combo), base_df)."""
    pair, combo, entry_df, htf_df, corr_df = args
    base = build_base_from_df(pair, entry_df, htf_df, corr_df)
    return (pair, combo), base


def _store_base(pair, combo, base, entry_df, cutoff, months, out_dir,
                base_cache, entry_cache, cutoffs, manifest, base_info):
    """Persist one freshly-built base to the resume cache and register it in the
    in-memory caches + manifest (shared by the serial and parallel build paths)."""
    cpath = _base_cache_path(out_dir, pair, combo, months)
    pickle.dump({"base": base, "entry_df": entry_df, "cutoff": cutoff},
                open(cpath, "wb"))
    base_cache[(pair, combo)] = base
    entry_cache[(pair, combo)] = entry_df
    cutoffs[(pair, combo)] = cutoff
    manifest["bases"][f"{pair}_{combo}_{months}mo"] = {
        "setups": int(len(base)),
        "cached_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    _save_manifest(manifest, out_dir)
    entry_name = combo.split("_")[1]
    base_info.append(f"{pair} {combo:<7} entry={entry_name}({len(entry_df):,}b)  "
                     f"setups={len(base):,}  window>={cutoff.date()}")


def simulate(base, entry_df, model_pt, target_rr, spread, cutoff,
             strategy_id="", pair="", combo=""):
    """Score, filter to last-2-months, sequential one-position sim.

    Records a RICH per-trade row (entry/exit time+price, stop, tp, direction,
    score, outcome, net R, spread cost in R, bars held) so the evaluation
    pipeline can compute drawdown / Monte-Carlo / portfolio metrics. Still keeps
    the legacy ``time``/``R``/``win`` fields the combined equity walk relies on.
    """
    if base.empty:
        return None
    model = get_model("perceptron", n_features=len(FEATURE_NAMES_V2))
    model.load_state_dict(torch.load(model_pt, map_location="cpu"))
    model.eval()
    X = torch.tensor(base[FEATURE_NAMES_V2].values, dtype=torch.float32)
    with torch.no_grad():
        base = base.copy()
        base["score"] = torch.sigmoid(model(X).squeeze(1)).numpy()

    base = base.sort_values("entry_time").reset_index(drop=True)
    recent = base[base["entry_time"] >= cutoff].reset_index(drop=True)

    highs = entry_df["high"].to_numpy(); lows = entry_df["low"].to_numpy()
    n = len(entry_df)
    trades = []
    free_bar = -1
    for _, r in recent.iterrows():
        if r["score"] < THRESHOLD:
            continue
        b = int(r["entry_bar"])
        if b <= free_bar:
            continue
        entry = r["entry_price"]; stop = r["stop"]; risk = r["risk"]
        bullish = r["dir_sign"] > 0
        tp = entry + target_rr * risk if bullish else entry - target_rr * risk
        outcome, exit_bar = None, min(n - 1, b + MAX_BARS)
        for j in range(b + 1, min(n, b + MAX_BARS + 1)):
            if bullish:
                sl_hit = lows[j] <= stop; tp_hit = highs[j] >= tp
            else:
                sl_hit = highs[j] >= stop; tp_hit = lows[j] <= tp
            if sl_hit and tp_hit:
                outcome, exit_bar = "loss", j; break
            if tp_hit:
                outcome, exit_bar = "win", j; break
            if sl_hit:
                outcome, exit_bar = "loss", j; break
        if outcome is None:
            continue
        gross = target_rr if outcome == "win" else -1.0
        spread_r = spread / risk               # entry spread charged, in R
        net = gross - spread_r
        exit_time = entry_df.index[exit_bar]
        trades.append({
            # legacy fields (combined equity walk / stats)
            "time": r["entry_time"], "R": net, "win": outcome == "win",
            # rich fields (evaluation pipeline canonical schema)
            "strategy_id": strategy_id, "pair": pair, "combo": combo,
            "rr": float(target_rr),
            "entry_time": r["entry_time"], "exit_time": exit_time,
            "direction": int(r["dir_sign"]),
            "entry_price": float(entry), "stop": float(stop),
            "take_profit": float(tp), "risk": float(risk),
            "score": float(r["score"]), "outcome": outcome,
            "r_multiple": net, "spread_cost": spread_r,
            "bars_held": int(exit_bar - b),
        })
        free_bar = exit_bar

    tdf = pd.DataFrame(trades)
    if tdf.empty:
        return {"trades": 0}
    nt = len(tdf); wins = int(tdf["win"].sum()); wr = wins / nt
    gw = tdf.loc[tdf["R"] > 0, "R"].sum(); gl = -tdf.loc[tdf["R"] <= 0, "R"].sum()
    pf = gw / gl if gl else float("inf")
    return {"trades": nt, "wins": wins, "win_rate": wr, "pf": pf,
            "exp_r": tdf["R"].mean(), "total_r": tdf["R"].sum(), "curve": tdf}


BASE_RISK_PCT = 0.5
RISK_FLOOR = BASE_RISK_PCT / 16.0


def compounded_equity(all_trades: pd.DataFrame, start_balance: float = 10_000.0):
    """Walk every trade in true chronological order (across all 15 strategies,
    since they run concurrently on one account), sizing each trade at
    risk_mult * BASE_RISK_PCT % of the CURRENT balance -- exactly how the fleet
    robot sizes orders. Each strategy keeps its OWN risk_mult: halved after
    that strategy's loss, reset to 1.0 after its win, floored at 1/16."""
    all_trades = all_trades.sort_values("time").reset_index(drop=True)
    balance = start_balance
    risk_mult = {s: 1.0 for s in all_trades["strategy"].unique()}
    curve = []
    for _, r in all_trades.iterrows():
        strat = r["strategy"]
        risk_pct = BASE_RISK_PCT * risk_mult[strat]
        risk_cash = balance * (risk_pct / 100.0)
        balance += risk_cash * r["R"]
        if r["win"]:
            risk_mult[strat] = 1.0
        else:
            risk_mult[strat] = max(RISK_FLOOR / BASE_RISK_PCT, risk_mult[strat] * 0.5)
        curve.append({"time": r["time"], "balance": balance})
    return balance, pd.DataFrame(curve)


# canonical trade-log columns the evaluation pipeline consumes
EXPORT_COLS = [
    "strategy_id", "pair", "combo", "rr",
    "entry_time", "exit_time", "direction",
    "entry_price", "stop", "take_profit", "risk",
    "score", "outcome", "r_multiple", "spread_cost", "bars_held",
    "split", "source", "run_ts",
]
DATA_DIR = "D:/MMC/mmc/evaluation/data"


# --------------------------------------------------------------------------- #
# Resume support: cache each (pair, combo) base to disk so an interrupted run
# (crash / MT5 disconnect / Ctrl-C) continues from where it left off instead of
# re-pulling candles and rebuilding every feature base from scratch. Cache +
# manifest live under the run's output dir so they follow --out.
# --------------------------------------------------------------------------- #

def _cache_dir(out_dir):
    return os.path.join(out_dir, "_cache")


def _manifest_path(out_dir):
    return os.path.join(out_dir, "_export_manifest.json")


def _base_cache_path(out_dir, pair, combo, months):
    return os.path.join(_cache_dir(out_dir), f"base_{pair}_{combo}_{months}mo.pkl")


def _load_manifest(out_dir):
    p = _manifest_path(out_dir)
    if os.path.exists(p):
        try:
            return json.load(open(p, "r", encoding="utf-8"))
        except Exception:
            pass
    return {"bases": {}, "last_run": None}


def _save_manifest(m, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    m["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    json.dump(m, open(_manifest_path(out_dir), "w", encoding="utf-8"),
              indent=2, default=str)


def _all72_strategies():
    """Every trained model as (pair, combo, rr-or-mode) — derived from the
    weights folder so it always matches what's on disk. rr modes -> int rr;
    structural modes (sth/ith/liq) are skipped here (no fixed target_rr)."""
    import glob, re
    out = []
    for pt in sorted(glob.glob(f"{WEIGHTS}/*.pt")):
        name = os.path.splitext(os.path.basename(pt))[0]   # EURUSD_H4_H1_rr4
        m = re.match(r"^([A-Z]+)_(.+)_rr(\d+)$", name)
        if m:
            out.append((m.group(1), m.group(2), int(m.group(3))))
    return out


def export_trade_log(valid, months, out_dir=DATA_DIR, run_ts=None):
    """Concatenate every strategy's rich trade rows into the canonical CSV,
    write a timestamped copy AND append+dedup into trades_master.csv so the
    sample size accumulates across runs (dedup key = strategy_id + entry_time)."""
    if not valid:
        print("  [export] no trades to export."); return None
    if run_ts is None:
        run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    frames = []
    for r in valid:
        c = r["curve"].copy()
        c["split"] = "OOS"
        c["source"] = "mt5_live"
        c["run_ts"] = run_ts
        frames.append(c)
    allt = pd.concat(frames, ignore_index=True)
    for col in EXPORT_COLS:
        if col not in allt.columns:
            allt[col] = pd.NA
    allt = allt[EXPORT_COLS]

    os.makedirs(out_dir, exist_ok=True)
    stamped = os.path.join(out_dir, f"trades_{run_ts}.csv")
    allt.to_csv(stamped, index=False)

    master = os.path.join(out_dir, "trades_master.csv")
    if os.path.exists(master):
        prev = pd.read_csv(master)
        combined = pd.concat([prev, allt], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=["strategy_id", "entry_time"], keep="last")
    else:
        combined = allt
    combined.to_csv(master, index=False)
    print(f"\n  [export] {len(allt)} trades -> {stamped}")
    print(f"  [export] master now holds {len(combined)} unique trades -> {master}")
    print(f"  next:  python -m mmc.evaluation --trades {master}")
    return master


def _scaled_pull(months):
    """Per-TF bar counts sized to the requested calendar window + warmup.
    Higher timeframes need far fewer bars for the same window (a 12-month H4
    pull is ~2k bars, not 36k), so we size each TF independently instead of
    scaling them all by the same factor."""
    return {tf: _needed_bars(tf, months) for tf in PULL}


def main(strat_list=None, months=MONTHS, out_dir=DATA_DIR, spread_pips=SPREAD_PIPS,
         evaluate=False, fresh=False, jobs=None):
    if strat_list is None:
        strat_list = TOP15
    pull = _scaled_pull(months)

    # run log: everything printed below is mirrored to data/run_<ts>.log
    run_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(out_dir, exist_ok=True)
    _tee = Tee(os.path.join(out_dir, f"run_{run_ts}.log")); _tee.__enter__()
    status = Status()
    _mode = "FRESH (rebuild all)" if fresh else "resumable (reuses base cache)"
    status.step(f"MT5 OOS export starting  |  {len(strat_list)} strategies  "
                f"|  {months}mo window  |  spread {spread_pips:g} pips  |  {_mode}")

    if not mt5.initialize():
        raise SystemExit(f"mt5.initialize() failed: {mt5.last_error()}")
    acct = mt5.account_info()
    print("=" * 92)
    print(f"  FRESH-FROM-MT5 OUT-OF-SAMPLE  |  last {months} months  |  score>={THRESHOLD}  "
          f"|  1 pos/strategy  |  spread charged  |  {len(strat_list)} strategies")
    print(f"  terminal: {acct.company} | login {acct.login} | "
          f"{'DEMO' if acct.trade_mode==mt5.ACCOUNT_TRADE_MODE_DEMO else 'REAL'}")
    print("=" * 92)

    # FIXED spread: spread_pips pips per instrument (pip = 10 x point), in price
    # units. info.point is just the instrument's tick size (not a broker spread
    # snapshot), used only to convert pips -> price.
    spreads = {}
    for s in ("EURUSD", "GBPUSD", "XAUUSD"):
        mt5.symbol_select(s, True)
        info = mt5.symbol_info(s)
        spreads[s] = spread_pips * 10.0 * info.point
    print(f"  fixed spread {spread_pips:g} pips:  " +
          "  ".join(f"{s}={spreads[s]:g}" for s in spreads))

    # ---- Phase 1: feature bases (resume cache + parallel build) ----
    base_cache = {}
    cutoffs = {}
    entry_cache = {}
    os.makedirs(_cache_dir(out_dir), exist_ok=True)
    manifest = _load_manifest(out_dir)
    uniq = sorted({(p, c) for p, c, _ in strat_list})
    base_info = []

    # 1a. instant-resume: load whatever bases are already cached from disk
    for pair, combo in uniq:
        cpath = _base_cache_path(out_dir, pair, combo, months)
        if not fresh and os.path.exists(cpath):
            d = pickle.load(open(cpath, "rb"))
            base_cache[(pair, combo)] = d["base"]
            entry_cache[(pair, combo)] = d["entry_df"]
            cutoffs[(pair, combo)] = d["cutoff"]
            age_h = (time.time() - os.path.getmtime(cpath)) / 3600.0
            base_info.append(f"{pair} {combo:<7} [cached {age_h:4.1f}h ago]  "
                             f"setups={len(d['base']):,}  window>={d['cutoff'].date()}")

    to_build = [(p, c) for (p, c) in uniq if (p, c) not in base_cache]
    status.step(f"{len(uniq)} feature bases: {len(base_cache)} cached (resumed), "
                f"{len(to_build)} to build")

    # 1b. pull candles for the missing ones (MT5 = one terminal connection, so
    #     do the pulls serially in the main process; the CPU build is parallel)
    pulled = {}
    pull_failed = []
    for j, (pair, combo) in enumerate(to_build, 1):
        status.bar(j - 1, len(to_build), f"pull {pair} {combo}")
        htf_name, entry_name = combo.split("_")
        entry_tf = _TF[entry_name]; htf_tf = _TF[htf_name]
        try:
            entry_df = get_bars(pair, entry_tf, pull[entry_tf])
            htf_df   = get_bars(pair, htf_tf, pull[htf_tf])
            corr_sym = _CORR.get(pair)
            corr_df  = get_bars(corr_sym, entry_tf, pull[entry_tf]) if corr_sym else None
        except RuntimeError as e:
            # one symbol/TF having no history shouldn't kill the whole run
            pull_failed.append((pair, combo, str(e)))
            continue
        cutoff = entry_df.index.max() - pd.Timedelta(days=30 * months)
        pulled[(pair, combo)] = (entry_df, htf_df, corr_df, cutoff)
    if to_build:
        status.bar(len(to_build), len(to_build), "candles pulled")
    for pair, combo, err in pull_failed:
        print(f"    !! SKIPPED {pair} {combo}: {err}")
    to_build = [pc for pc in to_build if pc in pulled]   # only build what we pulled

    # 1c. build the missing bases IN PARALLEL (CPU-bound, independent per combo)
    if to_build:
        n_jobs = jobs or (os.cpu_count() or 2)
        n_jobs = max(1, min(n_jobs, len(to_build)))
        status.step(f"building {len(to_build)} bases across {n_jobs} parallel "
                    f"worker(s) (the slow part)...")
        done = 0
        if n_jobs == 1:
            for pair, combo in to_build:
                entry_df, htf_df, corr_df, cutoff = pulled[(pair, combo)]
                base = build_base_from_df(pair, entry_df, htf_df, corr_df)
                _store_base(pair, combo, base, entry_df, cutoff, months, out_dir,
                            base_cache, entry_cache, cutoffs, manifest, base_info)
                done += 1
                status.bar(done, len(to_build), f"built {pair} {combo}")
        else:
            with ProcessPoolExecutor(max_workers=n_jobs) as ex:
                futs = {ex.submit(_build_base_task,
                                  (pair, combo, *pulled[(pair, combo)][:3])): (pair, combo)
                        for pair, combo in to_build}
                for fut in as_completed(futs):
                    pair, combo = futs[fut]
                    _, base = fut.result()
                    entry_df, _htf, _corr, cutoff = pulled[(pair, combo)]
                    _store_base(pair, combo, base, entry_df, cutoff, months, out_dir,
                                base_cache, entry_cache, cutoffs, manifest, base_info)
                    done += 1
                    status.bar(done, len(to_build), f"built {pair} {combo}")
        status.bar(len(to_build), len(to_build), "bases built")

    for line in base_info:
        print("    " + line)

    status.step(f"scoring & simulating {len(strat_list)} strategies...")
    print(f"\n  {'#':<3}{'strategy':<22}{'trades':>7}{'WR':>7}{'PF':>7}"
          f"{'expR':>8}{'totR':>8}")
    print("  " + "-" * 60)

    results = []
    for i, (pair, combo, rr) in enumerate(strat_list, 1):
        if (pair, combo) not in base_cache:
            print(f"  {i:<3}{pair}_{combo}_rr{rr}  (base unavailable - skipped)")
            continue
        base = base_cache[(pair, combo)]
        entry_df = entry_cache[(pair, combo)]
        model_pt = f"{WEIGHTS}/{pair}_{combo}_rr{rr}.pt"
        if not os.path.exists(model_pt):
            print(f"  {i:<3}{pair}_{combo}_rr{rr:<6} MISSING MODEL"); continue
        label = f"{pair}_{combo}_rr{rr}"        # canonical strategy_id
        r = simulate(base, entry_df, model_pt, float(rr),
                     spreads[pair], cutoffs[(pair, combo)],
                     strategy_id=label, pair=pair, combo=combo)
        if r is None or r["trades"] == 0:
            print(f"  {i:<3}{label:<22}{'0':>7}   (no trades in window)")
            results.append((label, r)); continue
        print(f"  {i:<3}{label:<22}{r['trades']:>7}{100*r['win_rate']:>6.1f}%"
              f"{r['pf']:>7.2f}{r['exp_r']:>+8.3f}{r['total_r']:>+8.1f}")
        r["curve"]["strategy"] = label
        results.append((label, r))

    # combined (strategies run in parallel & independent -> sum of R)
    valid = [r for _, r in results if r and r.get("trades")]
    print("  " + "-" * 60)
    tt = sum(r["trades"] for r in valid)
    tw = sum(r["wins"] for r in valid)
    tr = sum(r["total_r"] for r in valid)
    gw = sum(r["curve"].loc[r["curve"]["R"] > 0, "R"].sum() for r in valid)
    gl = sum(-r["curve"].loc[r["curve"]["R"] <= 0, "R"].sum() for r in valid)
    print(f"  {'':<3}{'FLEET COMBINED':<22}{tt:>7}{100*tw/max(tt,1):>6.1f}%"
          f"{gw/max(gl,1e-9):>7.2f}{tr/max(tt,1):>+8.3f}{tr:>+8.1f}")
    print()
    print(f"  {tt} trades over the last {months} months, {tw} winners "
          f"({100*tw/max(tt,1):.1f}% WR), net {tr:+.1f}R.")
    print(f"  At 0.5% risk per trade that is ~{0.5*tr:+.1f}% on the account "
          f"(simple, non-compounded).")

    # ---- realistic COMPOUNDED equity walk: every trade in true time order,
    # sized off the CURRENT balance, with per-strategy dynamic risk (halve on
    # loss, reset on win) -- exactly how the fleet robot sizes real orders.
    all_trades = pd.concat([r["curve"] for r in valid], ignore_index=True)
    start_bal = 10_000.0
    final_bal, eq_curve = compounded_equity(all_trades, start_bal)
    print(f"\n  COMPOUNDED walk-forward (all {len(valid)} strategies interleaved on ONE "
          f"${start_bal:,.0f} account,")
    print(f"  0.5% base risk, halved after each strategy's own loss, reset on win):")
    print(f"    start balance : ${start_bal:,.2f}")
    print(f"    end balance   : ${final_bal:,.2f}")
    print(f"    growth        : {100*(final_bal/start_bal - 1):+.1f}%  over {tt} trades / {months} months")
    peak = eq_curve["balance"].cummax()
    dd = ((eq_curve["balance"] - peak) / peak).min()
    print(f"    max drawdown  : {100*dd:.1f}%  (peak-to-trough on the balance curve)")

    print(f"\n  NOTE: idealized fills (exact SL/TP, no slippage/requote) and the")
    print(f"  config+seed were selected on history -> treat as an optimistic")
    print(f"  ceiling. The live demo forward test is the unbiased read.")

    # ---- persist the rich per-trade log for the evaluation pipeline ----
    master = export_trade_log(valid, months, out_dir, run_ts)

    mt5.shutdown()

    status.step(f"DONE in {status.elapsed():.1f}s - everything saved:")
    print(f"    - run log      : {os.path.join(out_dir, f'run_{run_ts}.log')}")
    print(f"    - trades (run) : {os.path.join(out_dir, f'trades_{run_ts}.csv')}")
    if master:
        print(f"    - trades master: {master}")
    print(f"    - resume cache : {_cache_dir(out_dir)}  ({_manifest_path(out_dir)})")
    _master = master or os.path.join(out_dir, "trades_master.csv")
    if evaluate and master:
        print(f"\n  --evaluate: chaining into the qualification pipeline now...")
    else:
        print(f"\n  Next -> evaluate & qualify:")
        print(f"    python -m mmc.evaluation --trades {_master}")
    _tee.__exit__()

    # optionally run step 2 automatically, in-process
    if evaluate and master:
        from mmc.evaluation.__main__ import main as _eval_main
        print("\n" + "=" * 92)
        _eval_main(["--trades", _master])


def _parse_args():
    import argparse
    ap = argparse.ArgumentParser(
        description="Fresh-from-MT5 OOS test + per-trade CSV export.")
    ap.add_argument("--months", type=int, default=MONTHS,
                    help=f"lookback window in months (default {MONTHS}); "
                         "widen to grow N past the qualification gate")
    ap.add_argument("--all72", action="store_true",
                    help="evaluate every trained model, not just the TOP-15 fleet")
    ap.add_argument("--out", default=DATA_DIR,
                    help="directory for the exported trade CSVs")
    ap.add_argument("--spread-pips", type=float, default=SPREAD_PIPS,
                    help=f"fixed spread charged per trade, in pips "
                         f"(default {SPREAD_PIPS}; pip = 10 x symbol point)")
    ap.add_argument("--evaluate", action="store_true",
                    help="automatically run `python -m mmc.evaluation` on the "
                         "master trade log right after export (one command does both)")
    ap.add_argument("--fresh", action="store_true",
                    help="ignore the resume cache and rebuild every feature base "
                         "from freshly-pulled MT5 candles")
    ap.add_argument("--jobs", type=int, default=0,
                    help="parallel worker processes for base building "
                         "(0 = auto / CPU count)")
    return ap.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    strat_list = _all72_strategies() if args.all72 else TOP15
    main(strat_list=strat_list, months=args.months, out_dir=args.out,
         spread_pips=args.spread_pips, evaluate=args.evaluate, fresh=args.fresh,
         jobs=(args.jobs or None))

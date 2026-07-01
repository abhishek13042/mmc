"""MMC BRAIN FLEET — run all TOP-15 strategies live on one demo account.

Deploys the 15 highest-expectancy configurations from the study, each as an
independent strategy in ONE process:

  * its own trained model (.pt), entry timeframe, HTF bias and 4R/3R target
  * its own MAGIC number, so positions never clash and each is managed alone
  * its own DYNAMIC RISK: base 0.5% of balance per trade; after a LOSS the next
    trade's risk is HALVED; after a WIN it resets to base. Floored at base/16.
  * one open position per strategy at a time (hedging account -> multiple
    strategies can hold the same symbol simultaneously)

All state (per-strategy risk multiplier, seen bars, open tickets) is persisted to
`_fleet_state.json` every cycle, so a restart resumes exactly where it left off.

SAFETY: demo-only, pinned to EXPECTED_LOGIN, spread filter, max-hold timeout.

RUN:  python examples/mt5_fleet_robot.py     (usually via run_fleet.bat on boot)
"""
from __future__ import annotations

import sys, os, json, time, logging, traceback
from datetime import datetime, timedelta

sys.path.insert(0, "D:/MMC")

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    raise SystemExit("MetaTrader5 not installed.  pip install MetaTrader5")

from mmc.core.types import Timeframe
from mmc.brain.live import LiveBrain

# =============================================================================
# CONFIG
# =============================================================================
EXPECTED_LOGIN = 109082333       # dedicated demo — robot refuses any other account
ALLOW_LIVE     = False

BASE_RISK_PCT  = 0.5             # base risk per trade (% of balance)
RISK_FLOOR     = BASE_RISK_PCT / 16.0   # never go below this after halving
THRESHOLD      = 0.50            # model take-trade score
MAX_SPREAD_POINTS = 40
MAX_HOLD_BARS  = 200
HISTORY_BARS   = 5000
SL_BUFFER      = 0.1

STATE_FILE = "D:/MMC/mmc/brain/weights/_fleet_state.json"
LOG_FILE   = "D:/MMC/mmc/brain/weights/_fleet.log"
WEIGHTS    = "D:/MMC/mmc/brain/weights"

_TF = {"M5": Timeframe.M5, "M15": Timeframe.M15, "H1": Timeframe.H1, "H4": Timeframe.H4}
_MT5_TF = {Timeframe.M5: mt5.TIMEFRAME_M5, Timeframe.M15: mt5.TIMEFRAME_M15,
           Timeframe.H1: mt5.TIMEFRAME_H1, Timeframe.H4: mt5.TIMEFRAME_H4}
_CORR = {"EURUSD": "GBPUSD", "GBPUSD": "EURUSD", "XAUUSD": None}

# TOP 15 by expectancy (pair, combo, rr) — combo = "<HTF>_<ENTRY>"
TOP15 = [
    ("GBPUSD", "H4_M15", 4), ("GBPUSD", "H4_H1", 4), ("GBPUSD", "H1_M15", 4),
    ("XAUUSD", "M15_M5", 4), ("EURUSD", "H4_M15", 4), ("EURUSD", "H4_H1", 4),
    ("EURUSD", "M15_M5", 4), ("EURUSD", "H1_M15", 4), ("XAUUSD", "H1_M15", 4),
    ("XAUUSD", "H4_H1", 4),  ("GBPUSD", "M15_M5", 4), ("XAUUSD", "H4_M15", 4),
    ("XAUUSD", "M15_M5", 3), ("GBPUSD", "H4_H1", 3),  ("EURUSD", "H4_H1", 3),
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(LOG_FILE, encoding="utf-8")])
log = logging.getLogger("fleet").info


# =============================================================================
# Strategy objects
# =============================================================================
class Strat:
    def __init__(self, idx, pair, combo, rr):
        htf_s, entry_s = combo.split("_")
        self.pair = pair
        self.combo = combo
        self.rr = rr
        self.entry_tf = _TF[entry_s]
        self.htf_tf = _TF[htf_s]
        self.corr = _CORR.get(pair)
        self.name = f"{pair}_{combo}_rr{rr}"
        self.magic = 770500 + idx
        self.brain = LiveBrain(f"{WEIGHTS}/{self.name}.pt",
                               target_rr=float(rr), threshold=THRESHOLD,
                               sl_buffer_atr=SL_BUFFER)
        self.risk_mult = 1.0        # dynamic; 1.0 = base risk
        self.last_bar = None        # last entry-TF bar time seen
        self.ticket = None          # current open position ticket


def build_strats():
    return [Strat(i, p, c, rr) for i, (p, c, rr) in enumerate(TOP15)]


# =============================================================================
# State persistence
# =============================================================================
def save_state(strats):
    st = {s.name: {"risk_mult": s.risk_mult,
                   "last_bar": s.last_bar.isoformat() if s.last_bar else None,
                   "ticket": s.ticket} for s in strats}
    tmp = STATE_FILE + ".tmp"
    json.dump(st, open(tmp, "w"), indent=2)
    os.replace(tmp, STATE_FILE)


def load_state(strats):
    if not os.path.exists(STATE_FILE):
        return
    try:
        st = json.load(open(STATE_FILE))
    except Exception:
        return
    for s in strats:
        d = st.get(s.name)
        if d:
            s.risk_mult = d.get("risk_mult", 1.0)
            s.ticket = d.get("ticket")
            lb = d.get("last_bar")
            s.last_bar = pd.Timestamp(lb) if lb else None


# =============================================================================
# MT5 helpers
# =============================================================================
def connect():
    if not mt5.initialize():
        raise SystemExit(f"mt5.initialize failed: {mt5.last_error()}")
    a = mt5.account_info()
    if a is None:
        raise SystemExit("terminal not logged in")
    is_demo = a.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
    log(f"Connected: {a.company} | login {a.login} | {'DEMO' if is_demo else 'REAL'} | {a.balance} {a.currency}")
    if not is_demo and not ALLOW_LIVE:
        raise SystemExit("refusing REAL account")
    if EXPECTED_LOGIN and a.login != EXPECTED_LOGIN:
        raise SystemExit(f"terminal on {a.login}, robot pinned to {EXPECTED_LOGIN} — refusing")
    return a


def get_bars(symbol, tf, n):
    rates = mt5.copy_rates_from_pos(symbol, _MT5_TF[tf], 0, n + 1)
    if rates is None or len(rates) < 50:
        return None
    df = pd.DataFrame(rates)
    df["datetime"] = pd.to_datetime(df["time"], unit="s")
    df = df.set_index("datetime").rename(columns={"tick_volume": "volume"})
    return df[["open", "high", "low", "close", "volume"]].astype(float).iloc[:-1]


def filling_mode(symbol):
    fm = mt5.symbol_info(symbol).filling_mode
    return mt5.ORDER_FILLING_IOC if fm & 2 else (mt5.ORDER_FILLING_FOK if fm & 1 else mt5.ORDER_FILLING_RETURN)


def lot_for_risk(symbol, entry, stop, risk_pct):
    info = mt5.symbol_info(symbol); acct = mt5.account_info()
    risk_cash = acct.balance * (risk_pct / 100.0)
    price_risk = abs(entry - stop)
    if price_risk <= 0:
        return 0.0
    loss_per_lot = (price_risk / info.trade_tick_size) * info.trade_tick_value
    if loss_per_lot <= 0:
        return 0.0
    step = info.volume_step or 0.01
    lot = max(info.volume_min, min(info.volume_max, round((risk_cash / loss_per_lot) / step) * step))
    return round(lot, 2)


def place_order(strat, sig):
    sym = strat.pair
    info = mt5.symbol_info(sym); tick = mt5.symbol_info_tick(sym)
    spread_pts = (tick.ask - tick.bid) / info.point
    if spread_pts > MAX_SPREAD_POINTS:
        log(f"  {strat.name}: skip, spread {spread_pts:.0f}pt"); return
    is_long = sig.direction == 1
    price = tick.ask if is_long else tick.bid
    risk_pct = max(RISK_FLOOR, BASE_RISK_PCT * strat.risk_mult)
    lot = lot_for_risk(sym, sig.entry, sig.stop, risk_pct)
    if lot <= 0:
        log(f"  {strat.name}: skip, lot 0"); return
    req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": lot,
           "type": mt5.ORDER_TYPE_BUY if is_long else mt5.ORDER_TYPE_SELL,
           "price": price, "sl": sig.stop, "tp": sig.tp, "deviation": 30,
           "magic": strat.magic, "comment": f"{strat.name[:20]} {int(sig.score*100)}",
           "type_time": mt5.ORDER_TIME_GTC, "type_filling": filling_mode(sym)}
    res = mt5.order_send(req)
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        log(f"  {strat.name}: ORDER FAIL {getattr(res,'retcode',None)} {mt5.last_error()}"); return
    strat.ticket = res.order
    log(f"  >>> {strat.name} {'BUY' if is_long else 'SELL'} {lot}lot @ {price:.5f} "
        f"SL {sig.stop:.5f} TP {sig.tp:.5f} risk {risk_pct:.3f}% score {sig.score:.0%}")


def update_closed(strat):
    """If the strategy's position closed, read its result and adjust risk."""
    if strat.ticket is None:
        return
    pos = mt5.positions_get(ticket=strat.ticket)
    if pos:               # still open
        return
    # closed — find the closing deal profit
    deals = mt5.history_deals_get(datetime.now() - timedelta(days=3), datetime.now() + timedelta(hours=1))
    profit = None
    if deals:
        mine = [d for d in deals if d.magic == strat.magic and d.entry == mt5.DEAL_ENTRY_OUT]
        if mine:
            profit = mine[-1].profit
    if profit is not None:
        if profit < 0:
            strat.risk_mult = max(RISK_FLOOR / BASE_RISK_PCT, strat.risk_mult * 0.5)
            log(f"  {strat.name}: LOSS -> risk halved to {BASE_RISK_PCT*strat.risk_mult:.3f}%")
        else:
            if strat.risk_mult != 1.0:
                log(f"  {strat.name}: WIN -> risk reset to {BASE_RISK_PCT:.3f}%")
            strat.risk_mult = 1.0
    strat.ticket = None


def manage_timeout(strat):
    if strat.ticket is None:
        return
    pos = mt5.positions_get(ticket=strat.ticket)
    if not pos:
        return
    p = pos[0]
    age = (time.time() - p.time) / (strat.entry_tf.minutes * 60)
    if age >= MAX_HOLD_BARS:
        tick = mt5.symbol_info_tick(strat.pair)
        ctype = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if p.type == mt5.POSITION_TYPE_BUY else tick.ask
        mt5.order_send({"action": mt5.TRADE_ACTION_DEAL, "symbol": strat.pair,
            "volume": p.volume, "type": ctype, "position": p.ticket, "price": price,
            "deviation": 30, "magic": strat.magic, "comment": "timeout",
            "type_filling": filling_mode(strat.pair)})
        log(f"  {strat.name}: timeout-closed #{p.ticket}")


# =============================================================================
# main loop
# =============================================================================
def main():
    connect()
    strats = build_strats()
    load_state(strats)
    log(f"FLEET armed: {len(strats)} strategies | base risk {BASE_RISK_PCT}% (halve on loss) | thr {THRESHOLD}")
    for s in strats:
        log(f"  - {s.name}  magic {s.magic}  entry {s.entry_tf.name}  {s.rr}R  risk {BASE_RISK_PCT*s.risk_mult:.3f}%")
    log("Running. (Ctrl-C to stop)")

    # smallest entry TF drives the poll rate
    poll = 20
    bars_cache = {}     # (symbol, tf) -> df, refreshed each cycle

    while True:
        try:
            bars_cache.clear()
            def bars(sym, tf):
                k = (sym, tf.name)
                if k not in bars_cache:
                    bars_cache[k] = get_bars(sym, tf, HISTORY_BARS)
                return bars_cache[k]

            for s in strats:
                # manage existing position first (timeout + close detection)
                manage_timeout(s)
                update_closed(s)

                entry_df = bars(s.pair, s.entry_tf)
                if entry_df is None or len(entry_df) < 100:
                    continue
                newest = entry_df.index[-1]
                if newest == s.last_bar:
                    continue                      # no new bar for this strategy yet
                s.last_bar = newest

                # already in a trade for THIS strategy?
                if s.ticket is not None and mt5.positions_get(ticket=s.ticket):
                    continue

                htf_df = bars(s.pair, s.htf_tf)
                corr_df = bars(s.corr, s.entry_tf) if s.corr else None
                if htf_df is None:
                    continue

                sig = s.brain.evaluate(entry_df, htf_df, corr_df, only_last_bar=True)
                if sig is not None:
                    log(f"[{newest}] {s.name} SETUP {'LONG' if sig.direction==1 else 'SHORT'} score {sig.score:.0%}")
                    place_order(s, sig)

            save_state(strats)
            time.sleep(poll)

        except KeyboardInterrupt:
            log("stopped by user"); break
        except Exception as e:
            log(f"loop error: {e}"); log(traceback.format_exc()); time.sleep(poll)

    mt5.shutdown()


if __name__ == "__main__":
    main()

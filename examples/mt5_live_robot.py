"""MMC BRAIN — MetaTrader 5 live trading robot (demo).

Runs the *real* trained model (identical to the backtest: mmc+atoz 55-feature
perceptron) against a live MT5 feed and places demo orders with a fixed 4R
take-profit — the target that won every pair/timeframe in the study.

    setup = a mitigated FVG whose model score >= THRESHOLD
    order = market entry, SL at the gap's far edge, TP at TARGET_RR x risk
    size  = risk RISK_PCT of balance per trade

SAFETY
  * Refuses to run on a LIVE account unless ALLOW_LIVE = True (default False).
  * One open position per symbol; skips new signals while in a trade.
  * Skips if spread > MAX_SPREAD_POINTS.

REQUIREMENTS
  pip install MetaTrader5
  MetaTrader 5 terminal installed + logged into your DEMO account, with
  "Algo Trading" enabled (button in the toolbar).

RUN
  python examples/mt5_live_robot.py
"""

from __future__ import annotations

import sys, os, time, logging
from datetime import datetime

sys.path.insert(0, "D:/MMC")

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    raise SystemExit("MetaTrader5 not installed.  Run:  pip install MetaTrader5")

from mmc.core.types import Timeframe
from mmc.brain.live import LiveBrain

# =============================================================================
# CONFIG  — edit these
# =============================================================================
SYMBOL       = "EURUSD"          # symbol to trade (must match your broker's name)
CORR_SYMBOL  = "GBPUSD"          # SMT correlated pair (None to disable)
ENTRY_TF     = Timeframe.H1      # entry timeframe
HTF          = Timeframe.H4      # higher-timeframe bias
WEIGHTS      = "D:/MMC/mmc/brain/weights/EURUSD_H4_H1_rr4.pt"  # model for this pair/combo

TARGET_RR    = 4.0               # take-profit in R (4R = best in the study)
THRESHOLD    = 0.50              # take the trade if score >= this (raise for fewer/better)
SL_BUFFER    = 0.1               # stop buffer beyond the gap, x ATR

RISK_PCT     = 1.0               # % of balance risked per trade
MAX_SPREAD_POINTS = 30           # skip if spread wider than this (points)
MAX_HOLD_BARS = 200              # flatten a trade older than this many entry-TF bars
HISTORY_BARS = 5000              # bars pulled each cycle (must cover all lookbacks)

MAGIC        = 770425            # order tag so the robot only manages its own trades
ALLOW_LIVE   = False             # HARD SAFETY: True required to trade a real account
LOGIN        = None              # set (login, password, server) to auto-login, else None
EXPECTED_LOGIN = 109082333       # HARD SAFETY: only trade THIS account (the dedicated
                                 # $10k demo). If the terminal is on any other login the
                                 # robot refuses to trade. Set None to disable the check.

# =============================================================================

_TF_MAP = {
    Timeframe.M5:  mt5.TIMEFRAME_M5,
    Timeframe.M15: mt5.TIMEFRAME_M15,
    Timeframe.H1:  mt5.TIMEFRAME_H1,
    Timeframe.H4:  mt5.TIMEFRAME_H4,
    Timeframe.D1:  mt5.TIMEFRAME_D1,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler("D:/MMC/mmc/brain/weights/_mt5_robot.log", encoding="utf-8")],
)
log = logging.getLogger("mmc-robot").info


# --------------------------------------------------------------------------- #
# MT5 helpers
# --------------------------------------------------------------------------- #

def connect():
    ok = mt5.initialize() if LOGIN is None else mt5.initialize(
        login=LOGIN[0], password=LOGIN[1], server=LOGIN[2])
    if not ok:
        raise SystemExit(f"mt5.initialize() failed: {mt5.last_error()}")

    acct = mt5.account_info()
    if acct is None:
        raise SystemExit("No account info — is the terminal logged in?")

    is_demo = acct.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
    log(f"Connected: {acct.company} | login {acct.login} | "
        f"{'DEMO' if is_demo else 'REAL'} | balance {acct.balance} {acct.currency}")
    if not is_demo and not ALLOW_LIVE:
        raise SystemExit("Refusing to run on a REAL account (set ALLOW_LIVE=True to override).")
    if EXPECTED_LOGIN is not None and acct.login != EXPECTED_LOGIN:
        raise SystemExit(
            f"Terminal is on account {acct.login}, but the robot is pinned to "
            f"{EXPECTED_LOGIN}. Switch the terminal to the dedicated demo, or set "
            f"EXPECTED_LOGIN=None. Refusing to trade the wrong account.")

    for s in {SYMBOL, CORR_SYMBOL} - {None}:
        if not mt5.symbol_select(s, True):
            raise SystemExit(f"Cannot select symbol {s}")
    return acct


def get_bars(symbol: str, tf: Timeframe, n: int) -> pd.DataFrame:
    """Return the last n CLOSED bars as an mmc-format DataFrame (drops the
    still-forming bar)."""
    rates = mt5.copy_rates_from_pos(symbol, _TF_MAP[tf], 0, n + 1)
    if rates is None or len(rates) < 10:
        raise RuntimeError(f"No rates for {symbol} {tf.name}: {mt5.last_error()}")
    df = pd.DataFrame(rates)
    df["datetime"] = pd.to_datetime(df["time"], unit="s")
    df = df.set_index("datetime")
    df = df.rename(columns={"tick_volume": "volume"})
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    return df.iloc[:-1]          # drop the last, still-forming bar


def has_open_position(symbol: str) -> bool:
    pos = mt5.positions_get(symbol=symbol)
    return any(p.magic == MAGIC for p in (pos or []))


def filling_mode(symbol: str):
    """Pick a filling mode the symbol actually allows (brokers differ — e.g.
    EURUSD may be FOK-only while XAUUSD allows IOC). Wrong mode = rejected order."""
    fm = mt5.symbol_info(symbol).filling_mode      # bitmask: 1=FOK, 2=IOC
    if fm & 2:
        return mt5.ORDER_FILLING_IOC
    if fm & 1:
        return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_RETURN


def lot_for_risk(symbol: str, entry: float, stop: float, risk_pct: float) -> float:
    info = mt5.symbol_info(symbol)
    acct = mt5.account_info()
    risk_cash = acct.balance * (risk_pct / 100.0)
    price_risk = abs(entry - stop)
    if price_risk <= 0:
        return 0.0
    # value of a 1-lot move of `price_risk`:
    ticks = price_risk / info.trade_tick_size
    loss_per_lot = ticks * info.trade_tick_value
    if loss_per_lot <= 0:
        return 0.0
    lot = risk_cash / loss_per_lot
    step = info.volume_step or 0.01
    lot = max(info.volume_min, min(info.volume_max, round(lot / step) * step))
    return round(lot, 2)


def place_order(sig, symbol: str):
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    spread_pts = (tick.ask - tick.bid) / info.point
    if spread_pts > MAX_SPREAD_POINTS:
        log(f"  skip {symbol}: spread {spread_pts:.0f}pt > {MAX_SPREAD_POINTS}")
        return None

    is_long = sig.direction == 1
    price = tick.ask if is_long else tick.bid
    lot = lot_for_risk(symbol, sig.entry, sig.stop, RISK_PCT)
    if lot <= 0:
        log(f"  skip {symbol}: computed lot 0")
        return None

    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if is_long else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sig.stop,
        "tp": sig.tp,
        "deviation": 20,
        "magic": MAGIC,
        "comment": f"MMCbrain {int(sig.score*100)}%",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode(symbol),
    }
    res = mt5.order_send(req)
    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
        log(f"  ORDER FAILED {symbol}: {getattr(res,'retcode',None)} {mt5.last_error()}")
        return None
    log(f"  >>> {'BUY' if is_long else 'SELL'} {symbol} {lot} lots @ {price:.5f}  "
        f"SL {sig.stop:.5f}  TP {sig.tp:.5f}  (score {sig.score:.0%}, {sig.rr:.0f}R)")
    return res


def manage_positions(symbol: str, tf: Timeframe):
    """Flatten any of our trades older than MAX_HOLD_BARS."""
    pos = mt5.positions_get(symbol=symbol) or []
    bar_secs = tf.minutes * 60
    now = time.time()
    for p in pos:
        if p.magic != MAGIC:
            continue
        age_bars = (now - p.time) / bar_secs
        if age_bars >= MAX_HOLD_BARS:
            tick = mt5.symbol_info_tick(symbol)
            close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = tick.bid if p.type == mt5.POSITION_TYPE_BUY else tick.ask
            mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol,
                "volume": p.volume, "type": close_type, "position": p.ticket,
                "price": price, "deviation": 20, "magic": MAGIC,
                "comment": "MMCbrain timeout", "type_filling": filling_mode(symbol),
            })
            log(f"  timeout-closed {symbol} #{p.ticket} ({age_bars:.0f} bars old)")


# --------------------------------------------------------------------------- #
# main loop
# --------------------------------------------------------------------------- #

def main():
    connect()
    brain = LiveBrain(WEIGHTS, target_rr=TARGET_RR, threshold=THRESHOLD,
                      sl_buffer_atr=SL_BUFFER)
    log(f"Robot armed: {SYMBOL} {HTF.name}->{ENTRY_TF.name}  "
        f"model={os.path.basename(WEIGHTS)}  TP={TARGET_RR}R  thr={THRESHOLD}  risk={RISK_PCT}%")
    log("Waiting for new closed bars...  (Ctrl-C to stop)")

    last_seen = None
    poll = max(5, ENTRY_TF.minutes * 60 // 20)   # poll ~20x per bar

    while True:
        try:
            entry_df = get_bars(SYMBOL, ENTRY_TF, HISTORY_BARS)
            newest = entry_df.index[-1]

            if newest != last_seen:                 # a new bar just CLOSED
                last_seen = newest
                htf_df = get_bars(SYMBOL, HTF, HISTORY_BARS)
                corr_df = get_bars(CORR_SYMBOL, ENTRY_TF, HISTORY_BARS) if CORR_SYMBOL else None

                manage_positions(SYMBOL, ENTRY_TF)

                if has_open_position(SYMBOL):
                    log(f"[{newest}] already in a {SYMBOL} trade — hold")
                else:
                    sig = brain.evaluate(entry_df, htf_df, corr_df, only_last_bar=True)
                    if sig is None:
                        log(f"[{newest}] no qualifying setup")
                    else:
                        log(f"[{newest}] SETUP {'LONG' if sig.direction==1 else 'SHORT'} "
                            f"score={sig.score:.0%} entry={sig.entry:.5f} "
                            f"SL={sig.stop:.5f} TP={sig.tp:.5f}")
                        place_order(sig, SYMBOL)

            time.sleep(poll)

        except KeyboardInterrupt:
            log("Stopped by user.")
            break
        except Exception as e:
            log(f"loop error: {e}")
            time.sleep(poll)

    mt5.shutdown()


if __name__ == "__main__":
    main()

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime

# Setup paths for imports
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
MMC_DIR = os.path.join(ROOT_DIR, 'mmc_backtest')
if ROOT_DIR not in sys.path: sys.path.insert(0, ROOT_DIR)
if MMC_DIR not in sys.path: sys.path.insert(0, MMC_DIR)

from modules.data_engine import fetch_candles
from mmc_backtest.strategies.strategy_5_candle_science.scanner import scan_candle_science

def calculate_performance(trades):
    if not trades:
        return {
            "total_signals": 0, "wins": 0, "losses": 0, "neutrals": 0,
            "win_rate_pct": 0, "total_rr": 0, "avg_rr": 0
        }
    
    wins = [t for t in trades if t['result'] == 'WIN']
    losses = [t for t in trades if t['result'] == 'LOSS']
    neutrals = [t for t in trades if t['result'] == 'NEUTRAL']
    
    total_completed = len(wins) + len(losses)
    win_rate = (len(wins) / total_completed * 100) if total_completed > 0 else 0
    total_rr = sum(t['rr_achieved'] for t in trades)
    
    return {
        "total_signals": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "neutrals": len(neutrals),
        "win_rate_pct": round(win_rate, 2),
        "total_rr": round(total_rr, 2),
        "avg_rr": round(total_rr / len(trades), 2) if trades else 0
    }

def run_backtest(instrument, timeframe=None, data_dir=None, n_candles=2000, **kwargs):
    """
    Run backtest for Strategy 5 (Candle Science).
    Adaptive LTF selection based on HTF.
    """
    # Accept direct htf/ltf if provided by master runner
    htf = kwargs.get('htf', timeframe).upper() if (timeframe or 'htf' in kwargs) else 'DAILY'
    ltf = kwargs.get('ltf')
    
    if not ltf:
        # Map HTF to LTF for refinement
        tf_map = {
            'DAILY': '1H',
            '4H': '15M',
            '1H': '5M',
            '15M': '1M'
        }
        ltf = tf_map.get(htf, '15M')
    
    print(f"Starting Strategy 5 Backtest: {instrument} {htf} (LTF: {ltf})")
    
    # 1. Load Data
    try:
        df_htf = fetch_candles(instrument, htf, data_dir)
        df_ltf = fetch_candles(instrument, ltf, data_dir)
    except Exception as e:
        print(f"Error loading data for S5: {e}")
        return None
        
    if df_htf is None or df_ltf is None:
        return None
        
    # Limit for backtest speed
    df_htf_sample = df_htf.tail(n_candles // 10 if htf == 'DAILY' else n_candles).copy()
    
    print(f"Scanning for signals...")
    signals = scan_candle_science(df_htf_sample, df_ltf, instrument, htf, ltf)
    print(f"Found {len(signals)} signals.")
    
    # 3. Build Datetime to Index mapping for fast lookup
    dt_to_idx = {str(dt): idx for idx, dt in enumerate(df_ltf['datetime'])}
    
    trades = []
    for sig in signals:
        signal_dt = str(sig['signal_datetime'])
        if signal_dt not in dt_to_idx: continue
        
        start_idx = dt_to_idx[signal_dt] + 1
        direction = sig['direction']
        entry = sig['entry_price']
        sl = sig['stop_loss']
        tp_2r = sig['tp_2r']
        tp_4r = sig['tp_4r']
        
        outcome = sig.copy()
        outcome.update({
            'result': 'PENDING',
            'rr_achieved': 0.0,
            'exit_datetime': None,
            'exit_price': None,
            'candles_held': 0
        })
        
        # Simulate on LTF
        max_lookahead = 200 # More lookahead for LTF
        for j in range(start_idx, min(start_idx + max_lookahead, len(df_ltf))):
            curr_candle = df_ltf.iloc[j]
            outcome['candles_held'] += 1
            
            if direction == 'BULLISH':
                if curr_candle['low'] <= sl:
                    outcome['result'] = 'LOSS'; outcome['rr_achieved'] = -1.0
                    outcome['exit_datetime'] = curr_candle['datetime']; outcome['exit_price'] = sl
                    break
                if curr_candle['high'] >= tp_4r:
                    outcome['result'] = 'WIN'
                    risk = abs(entry - sl)
                    outcome['rr_achieved'] = round(abs(tp_4r - entry) / risk, 2)
                    outcome['exit_datetime'] = curr_candle['datetime']; outcome['exit_price'] = tp_4r
                    break
            else: # BEARISH
                if curr_candle['high'] >= sl:
                    outcome['result'] = 'LOSS'; outcome['rr_achieved'] = -1.0
                    outcome['exit_datetime'] = curr_candle['datetime']; outcome['exit_price'] = sl
                    break
                if curr_candle['low'] <= tp_4r:
                    outcome['result'] = 'WIN'
                    risk = abs(entry - sl)
                    outcome['rr_achieved'] = round(abs(tp_4r - entry) / risk, 2)
                    outcome['exit_datetime'] = curr_candle['datetime']; outcome['exit_price'] = tp_4r
                    break
                    
        if outcome['result'] == 'PENDING':
            # Check 2R fallback
            for j in range(start_idx, min(start_idx + max_lookahead, len(df_ltf))):
                c = df_ltf.iloc[j]
                if (direction == 'BULLISH' and c['high'] >= tp_2r) or (direction == 'BEARISH' and c['low'] <= tp_2r):
                    outcome['result'] = 'WIN'; outcome['rr_achieved'] = 2.0
                    outcome['exit_datetime'] = c['datetime']; outcome['exit_price'] = tp_2r
                    break
            if outcome['result'] == 'PENDING':
                outcome['result'] = 'NEUTRAL'; outcome['rr_achieved'] = 0.0
        
        trades.append(outcome)
        
    stats = calculate_performance(trades)
    
    # Extra stats
    if trades:
        type_dist = {}
        bias_dist = {'HIGH': 0, 'MEDIUM': 0}
        for t in trades:
            ct = t['htf_candle_type']
            type_dist[ct] = type_dist.get(ct, 0) + 1
            bc = t['bias_confidence']
            bias_dist[bc] = bias_dist.get(bc, 0) + 1
            
        stats['htf_candle_type_distribution'] = type_dist
        stats['bias_confidence_breakdown'] = bias_dist
        
    return {
        "instrument": instrument,
        "htf": htf,
        "ltf": ltf,
        "total_signals": len(trades),
        "trades": trades,
        "stats": stats
    }

def main():
    instrument = "EURUSD"; htf = "DAILY"; ltf = "1H"
    results = run_backtest(instrument, htf, ltf)
    
    if "error" in results:
        print(f"Error: {results['error']}")
        return
        
    print(f"Signals: {results['total_signals']} | Win Rate: {results['stats']['win_rate_pct']}%")
    
    output_dir = "mmc_backtest/backtest/results"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"s5_{instrument}_{htf}_{ltf}.json")
    
    with open(output_file, "w") as f:
        json.dump(results, f, indent=4, default=str)
    print(f"Results saved to: {output_file}")

if __name__ == "__main__":
    main()

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
from mmc_backtest.strategies.strategy_3_fva_good.scanner import scan_fva_good

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

def run_strategy_backtest(df, scan_func, instrument, timeframe):
    """
    Simulate trades based on discovered signals.
    """
    print(f"Scanning {len(df)} candles for signals...")
    signals = scan_func(df, instrument, timeframe)
    print(f"Found {len(signals)} signals.")
    trades = []
    
    for sig in signals:
        signal_dt = sig['signal_datetime']
        idx_list = df.index[df['datetime'] == signal_dt].tolist()
        if not idx_list:
            continue
        
        start_idx = idx_list[0] + 1
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
        
        # Walk forward simulation
        max_lookahead = 100
        for j in range(start_idx, min(start_idx + max_lookahead, len(df))):
            curr_candle = df.iloc[j]
            outcome['candles_held'] += 1
            
            if direction == 'BULLISH':
                # SL check
                if curr_candle['low'] <= sl:
                    outcome['result'] = 'LOSS'
                    outcome['rr_achieved'] = -1.0
                    outcome['exit_datetime'] = curr_candle['datetime']
                    outcome['exit_price'] = sl
                    break
                # TP 4R check
                if curr_candle['high'] >= tp_4r:
                    outcome['result'] = 'WIN'
                    risk = abs(entry - sl)
                    outcome['rr_achieved'] = round(abs(tp_4r - entry) / risk, 2)
                    outcome['exit_datetime'] = curr_candle['datetime']
                    outcome['exit_price'] = tp_4r
                    break
            else: # BEARISH
                if curr_candle['high'] >= sl:
                    outcome['result'] = 'LOSS'
                    outcome['rr_achieved'] = -1.0
                    outcome['exit_datetime'] = curr_candle['datetime']
                    outcome['exit_price'] = sl
                    break
                if curr_candle['low'] <= tp_4r:
                    outcome['result'] = 'WIN'
                    risk = abs(entry - sl)
                    outcome['rr_achieved'] = round(abs(tp_4r - entry) / risk, 2)
                    outcome['exit_datetime'] = curr_candle['datetime']
                    outcome['exit_price'] = tp_4r
                    break
                    
        if outcome['result'] == 'PENDING':
            # Check if it hit 2R
            hit_2r = False
            for j in range(start_idx, min(start_idx + max_lookahead, len(df))):
                c = df.iloc[j]
                if (direction == 'BULLISH' and c['high'] >= tp_2r) or (direction == 'BEARISH' and c['low'] <= tp_2r):
                    hit_2r = True
                    outcome['result'] = 'WIN'
                    outcome['rr_achieved'] = 2.0
                    outcome['exit_datetime'] = c['datetime']
                    outcome['exit_price'] = tp_2r
                    break
            if not hit_2r:
                outcome['result'] = 'NEUTRAL'
                outcome['rr_achieved'] = 0.0
        
        trades.append(outcome)
        
    return {
        "instrument": instrument,
        "timeframe": timeframe,
        "total_trades": len(trades),
        "trades": trades,
        "stats": calculate_performance(trades)
    }

def main():
    instrument = "EURUSD"
    timeframe = "1H"
    
    print(f"Starting Strategy 3 (Good FVA) Backtest: {instrument} {timeframe}")
    
    try:
        df = fetch_candles(instrument, timeframe)
        if df is None or df.empty:
            print("Failed to load data.")
            return

        # Verification sample
        df_sample = df.tail(1000).copy()
        
        results = run_strategy_backtest(df_sample, scan_fva_good, instrument, timeframe)
        
        # Extra stats
        if results['total_trades'] > 0:
            cs_dist = {}
            fvg_dist = {'PFVG': 0, 'BFVG': 0}
            
            for t in results['trades']:
                cs_key = f"{t['candle_science_bias']}_{t['candle_science_confidence']}"
                cs_dist[cs_key] = cs_dist.get(cs_key, 0) + 1
                fvg_type = t['overlapping_fvg_type']
                if fvg_type in fvg_dist:
                    fvg_dist[fvg_type] += 1
            
            results['stats']['candle_science_distribution'] = cs_dist
            results['stats']['bfvg_vs_pfvg_count'] = fvg_dist
            
        results['note'] = "Good FVA has 2 probability arrays. Expected lower WR than Ideal (3 arrays)."

        output_dir = "mmc_backtest/backtest/results"
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = os.path.join(output_dir, "s3_EURUSD_1H.json")
        with open(output_file, "w") as f:
            json.dump(results, f, indent=4, default=str)
            
        print(f"Results saved to: {output_file}")
        print(f"Total Trades: {results['total_trades']} | Win Rate: {results['stats']['win_rate_pct']}%")
    except Exception as e:
        print(f"Error in backtest: {e}")

if __name__ == "__main__":
    main()

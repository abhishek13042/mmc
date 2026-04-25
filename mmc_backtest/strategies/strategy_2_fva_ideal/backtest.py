import sys
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime
import csv

# Add project root and mmc_backtest folder to path for imports to work
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
MMC_DIR = os.path.join(ROOT_DIR, 'mmc_backtest')
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, MMC_DIR)

from mmc_backtest.backtest.data_loader import fetch_candles
from mmc_backtest.strategies.strategy_2_fva_ideal.scanner import scan_fva_ideal

def run_backtest(instrument, timeframe, data_dir=None):
    """
    Full backtest runner for Strategy 2 - FVA Ideal.
    """
    print(f"Starting Strategy 2 Backtest: {instrument} {timeframe}")
    
    # 1. Load Data
    try:
        df = fetch_candles(instrument, timeframe, data_dir)
        print(f"Loaded {len(df)} candles for {instrument} {timeframe}")
    except Exception as e:
        print(f"Error loading data: {e}")
        return None
        
    # 2. Scan for Signals
    print("Scanning for Signals...")
    # Minimum window for scan: 50 candles (to establish context)
    # Start scanning from candle index 50 onward
    # Use df.iloc[:i] for walk-forward simulation (no lookahead)
    signals = scan_fva_ideal(df, instrument, timeframe)
    print(f"Found {len(signals)} signals.")
    
    if not signals:
        return {
            "instrument": instrument, 
            "timeframe": timeframe, 
            "total_signals": 0, 
            "trades": [],
            "stats": {
                "total_signals": 0, "wins": 0, "losses": 0, "neutrals": 0,
                "win_rate_pct": 0, "total_rr": 0, "avg_rr": 0,
                "nested_fva_used_pct": 0, "avg_fva_size_pips": 0, "ideal_fva_count": 0
            }
        }
        
    # 3. Simulate Trades
    # 3. Build Datetime to Index mapping for fast lookup
    dt_to_idx = {str(dt): idx for idx, dt in enumerate(df['datetime'])}
    
    trades = []
    nested_used_count = 0
    total_fva_size = 0
    
    for sig in signals:
        signal_dt = str(sig['signal_datetime'])
        if signal_dt not in dt_to_idx:
            continue
        
        start_idx = dt_to_idx[signal_dt] + 1
        
        direction = sig['direction']
        entry = sig['entry_price']
        sl = sig['stop_loss']
        tp_2r = sig['tp_2r']
        tp_4r = sig['tp_4r']
        
        total_fva_size += (sig['fva_high'] - sig['fva_low'])
        if sig['nested_fva_high'] is not None or sig['nested_fva_low'] is not None:
            nested_used_count += 1
            
        outcome = {
            'signal_datetime': signal_dt,
            'direction': direction,
            'entry_price': entry,
            'stop_loss': sl,
            'tp_2r': tp_2r,
            'tp_4r': tp_4r,
            'result': 'PENDING',
            'rr_achieved': 0.0,
            'exit_datetime': None,
            'exit_price': None,
            'candles_held': 0,
            'risk_pips': sig['risk_pips'],
            'ofl_probability': sig['ofl_probability']
        }
        
        # Simulate walking forward (max 100 candles for S2)
        max_lookahead = 100
        
        for j in range(start_idx, min(start_idx + max_lookahead, len(df))):
            curr_candle = df.iloc[j]
            outcome['candles_held'] += 1
            
            if direction == 'BULLISH':
                # SL check first
                if curr_candle['low'] <= sl:
                    outcome['result'] = 'LOSS'
                    outcome['rr_achieved'] = -1.0
                    outcome['exit_datetime'] = curr_candle['datetime']
                    outcome['exit_price'] = sl
                    break
                # TP 4R check (Extended win)
                if curr_candle['high'] >= tp_4r:
                    outcome['result'] = 'WIN'
                    risk = abs(entry - sl)
                    outcome['rr_achieved'] = round(abs(tp_4r - entry) / risk, 2)
                    outcome['exit_datetime'] = curr_candle['datetime']
                    outcome['exit_price'] = tp_4r
                    break
                # TP 2R check
                if curr_candle['high'] >= tp_2r:
                    # Keep going to see if we hit 4R, but mark as WIN 2R for now if it exits later?
                    # Actually, logic says "WIN at tp_2r, rr_achieved=2.0. Extended win at tp_4r, rr_achieved=4.0."
                    # This implies if it hits 2R, it's a win. If it continues to 4R, it's a better win.
                    # We continue the loop to check for 4R or SL.
                    pass
            else: # BEARISH
                # SL check first
                if curr_candle['high'] >= sl:
                    outcome['result'] = 'LOSS'
                    outcome['rr_achieved'] = -1.0
                    outcome['exit_datetime'] = curr_candle['datetime']
                    outcome['exit_price'] = sl
                    break
                # TP 4R check
                if curr_candle['low'] <= tp_4r:
                    outcome['result'] = 'WIN'
                    risk = abs(entry - sl)
                    outcome['rr_achieved'] = round(abs(tp_4r - entry) / risk, 2)
                    outcome['exit_datetime'] = curr_candle['datetime']
                    outcome['exit_price'] = tp_4r
                    break
                # TP 2R check
                if curr_candle['low'] <= tp_2r:
                    pass
                    
        if outcome['result'] == 'PENDING':
            # Check if it at least hit 2R during the 100 candles
            hit_2r = False
            for j in range(start_idx, min(start_idx + max_lookahead, len(df))):
                c = df.iloc[j]
                if (direction == 'BULLISH' and c['high'] >= tp_2r) or (direction == 'BEARISH' and c['low'] <= tp_2r):
                    hit_2r = True
                    # Let's see when it hit 2R
                    outcome['result'] = 'WIN'
                    outcome['rr_achieved'] = 2.0
                    outcome['exit_datetime'] = c['datetime']
                    outcome['exit_price'] = tp_2r
                    break
            
            if not hit_2r:
                outcome['result'] = 'NEUTRAL'
                outcome['rr_achieved'] = 0.0
            
        trades.append(outcome)
        
    # 4. Calculate Statistics
    from mmc_backtest.modules.video1_pd_arrays import get_pip_multiplier
    pip_mult = get_pip_multiplier(instrument)
    
    stats = calculate_performance(trades)
    stats['nested_fva_used_pct'] = round((nested_used_count / len(signals) * 100) if signals else 0, 2)
    stats['avg_fva_size_pips'] = round((total_fva_size / len(signals) * pip_mult) if signals else 0, 2)
    stats['ideal_fva_count'] = len(signals)
    
    results = {
        "instrument": instrument,
        "timeframe": timeframe,
        "strategy": "FVA_IDEAL",
        "generated_at": datetime.now().isoformat(),
        "stats": stats,
        "trades": trades
    }
    
    return results

def calculate_performance(trades):
    if not trades:
        return {}
    
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

def save_results(results, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to: {output_path}")

if __name__ == '__main__':
    # Test run
    try:
        results = run_backtest('EURUSD', '1H')
        if results:
            print(f"Signals: {results['stats']['total_signals']} | WR: {results['stats']['win_rate_pct']:.1f}%")
            save_results(results, 'mmc_backtest/backtest/results/s2_EURUSD_1H.json')
    except Exception as e:
        print(f"Error in backtest: {e}")

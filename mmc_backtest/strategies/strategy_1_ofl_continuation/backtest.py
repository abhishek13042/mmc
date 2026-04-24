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
from mmc_backtest.strategies.strategy_1_ofl_continuation.scanner import scan_ofl_continuation

def run_backtest(instrument, timeframe, data_dir=None):
    """
    Full backtest runner for Strategy 1.
    """
    print(f"Starting Strategy 1 Backtest: {instrument} {timeframe}")
    
    # 1. Load Data
    try:
        df = fetch_candles(instrument, timeframe, data_dir)
        print(f"Loaded {len(df)} candles for {instrument} {timeframe}")
    except Exception as e:
        print(f"Error loading data: {e}")
        return None
        
    # 2. Scan for Signals
    print("Scanning for Signals...")
    signals = scan_ofl_continuation(df, instrument, timeframe)
    print(f"Found {len(signals)} signals.")
    
    if not signals:
        return {
            "instrument": instrument, 
            "timeframe": timeframe, 
            "total_signals": 0, 
            "trades": [],
            "stats": {
                "total_signals": 0, "wins": 0, "losses": 0, "neutrals": 0,
                "win_rate_pct": 0, "total_rr": 0, "avg_rr": 0
            }
        }
        
    # 3. Simulate Trades
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
        tp_fixed = sig['tp_2r']
        tp_erl = sig.get('tp_erl') # Institutional target
        
        # Use ERL as target if it offers better RR, else fix at 2R
        # Actually, let's just stick to ERL for "Full Understanding"
        tp_target = tp_erl if tp_erl else tp_fixed
        
        outcome = {
            'signal_datetime': signal_dt,
            'direction': direction,
            'entry_price': entry,
            'stop_loss': sl,
            'tp_target': tp_target,
            'tp_fixed_2r': tp_fixed,
            'result': 'PENDING',
            'rr_achieved': 0.0,
            'exit_datetime': None,
            'exit_price': None,
            'candles_held': 0,
            'risk_pips': sig['risk_pips'],
            'ofl_probability': sig['ofl_probability']
        }
        
        # Simulate walking forward (max 1000 candles for 5M/15M)
        max_lookahead = 1000 if timeframe in ['5M', '15M'] else 200
        
        for j in range(start_idx, min(start_idx + max_lookahead, len(df))):
            curr_candle = df.iloc[j]
            outcome['candles_held'] += 1
            
            if direction == 'BULLISH':
                # Check SL
                if curr_candle['low'] <= sl:
                    outcome['result'] = 'LOSS'
                    outcome['rr_achieved'] = -1.0
                    outcome['exit_datetime'] = curr_candle['datetime']
                    outcome['exit_price'] = sl
                    break
                # Check TP Target
                if curr_candle['high'] >= tp_target:
                    outcome['result'] = 'WIN'
                    risk = abs(entry - sl)
                    outcome['rr_achieved'] = round(abs(tp_target - entry) / risk, 2)
                    outcome['exit_datetime'] = curr_candle['datetime']
                    outcome['exit_price'] = tp_target
                    break
            else: # BEARISH
                # Check SL
                if curr_candle['high'] >= sl:
                    outcome['result'] = 'LOSS'
                    outcome['rr_achieved'] = -1.0
                    outcome['exit_datetime'] = curr_candle['datetime']
                    outcome['exit_price'] = sl
                    break
                # Check TP Target
                if curr_candle['low'] <= tp_target:
                    outcome['result'] = 'WIN'
                    risk = abs(entry - sl)
                    outcome['rr_achieved'] = round(abs(tp_target - entry) / risk, 2)
                    outcome['exit_datetime'] = curr_candle['datetime']
                    outcome['exit_price'] = tp_target
                    break
                    
        if outcome['result'] == 'PENDING':
            outcome['result'] = 'NEUTRAL'
            outcome['rr_achieved'] = 0.0
            
        trades.append(outcome)
        
    # 4. Calculate Statistics
    stats = calculate_performance(trades)
    
    results = {
        "instrument": instrument,
        "timeframe": timeframe,
        "strategy": "OFL_CONTINUATION",
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

def save_strategy_results(results, instrument, timeframe):
    # LOCAL results folder inside Strategy 1
    base_dir = os.path.join(os.path.dirname(__file__), 'results')
    os.makedirs(base_dir, exist_ok=True)
    
    filename_base = f"strategy_1_{instrument.lower()}_{timeframe.lower()}"
    
    # Save JSON
    json_path = os.path.join(base_dir, f"{filename_base}.json")
    with open(json_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Save CSV
    csv_path = os.path.join(base_dir, f"{filename_base}.csv")
    if results['trades']:
        keys = results['trades'][0].keys()
        with open(csv_path, 'w', newline='') as f:
            dict_writer = csv.DictWriter(f, keys)
            dict_writer.writeheader()
            dict_writer.writerows(results['trades'])
            
    print(f"Results saved to: {json_path} and {csv_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='MMC Strategy 1 Backtest')
    parser.add_argument('--instrument', type=str, default='EURUSD', help='Instrument')
    parser.add_argument('--timeframe', type=str, default='DAILY', help='Timeframe')
    
    args = parser.parse_args()
    
    res = run_backtest(args.instrument, args.timeframe)
    if res:
        save_strategy_results(res, args.instrument, args.timeframe)
        print(f"Win Rate: {res['stats']['win_rate_pct']}% | Total RR: {res['stats']['total_rr']}")

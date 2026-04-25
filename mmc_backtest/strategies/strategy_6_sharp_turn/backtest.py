import pandas as pd
import numpy as np
import os
import json
from datetime import datetime
from modules.data_engine import fetch_candles
from strategies.strategy_6_sharp_turn.scanner import scan_sharp_turn

def run_backtest(instrument, context_tf, entry_tf, data_dir=None) -> dict:
    """
    Run Strategy 6 Backtest
    """
    print(f"Starting Strategy 6 Backtest for {instrument} {context_tf}/{entry_tf}...")
    
    df_context = fetch_candles(instrument, context_tf)
    df_entry = fetch_candles(instrument, entry_tf)
    
    if df_context is None or df_entry is None:
        return {"error": "Failed to load data"}
        
    signals = scan_sharp_turn(df_context, df_entry, instrument, context_tf, entry_tf)
    
    results = []
    total_signals = len(signals)
    
    if total_signals == 0:
        return {
            'instrument': instrument,
            'context_tf': context_tf,
            'entry_tf': entry_tf,
            'total_signals': 0,
            'win_rate_pct': 0,
            'avg_candles_to_form_fvg_out': 0,
            'context_target_hit_pct': 0,
            'tp2r_hit_pct': 0,
            'trades': []
        }
        
    candles_to_form_list = []
    
    # 3. Build Datetime to Index mapping for fast lookup
    dt_to_idx = {str(dt): idx for idx, dt in enumerate(df_entry['datetime'])}
    
    for sig in signals:
        # Start simulation from sig_datetime
        sig_dt_str = str(sig['signal_datetime'])
        if sig_dt_str not in dt_to_idx:
            continue
        sig_idx = dt_to_idx[sig_dt_str]
        # Get candles after signal
        trade_data = df_entry.iloc[sig_idx + 1 : sig_idx + 101]
        
        direction = sig['direction']
        stop_loss = sig['stop_loss']
        tp_2r = sig['tp_2r']
        context_target = sig['context_target']
        
        outcome = 'NEUTRAL'
        exit_price = None
        exit_time = None
        win_type = None # 'CONTEXT' or 'TP2R'
        
        for idx, row in trade_data.iterrows():
            # Check Stop Loss
            if direction == 'BULLISH':
                if row['low'] <= stop_loss:
                    outcome = 'LOSS'
                    exit_price = stop_loss
                    exit_time = row['datetime']
                    break
                
                # Check Targets (Whichever hit first in same candle? We'll assume TP2R is usually closer or reached first if both hit)
                # Actually, check which one is closer.
                targets = []
                if row['high'] >= tp_2r: targets.append(('TP2R', tp_2r))
                if row['high'] >= context_target: targets.append(('CONTEXT', context_target))
                
                if targets:
                    outcome = 'WIN'
                    # If both hit, which one is "first"? Usually the closer one.
                    targets.sort(key=lambda x: x[1]) # Nearest target first
                    win_type, exit_price = targets[0]
                    exit_time = row['datetime']
                    break
                    
            else: # BEARISH
                if row['high'] >= stop_loss:
                    outcome = 'LOSS'
                    exit_price = stop_loss
                    exit_time = row['datetime']
                    break
                    
                targets = []
                if row['low'] <= tp_2r: targets.append(('TP2R', tp_2r))
                if row['low'] <= context_target: targets.append(('CONTEXT', context_target))
                
                if targets:
                    outcome = 'WIN'
                    targets.sort(key=lambda x: x[1], reverse=True) # Nearest target first (highest price for bearish)
                    win_type, exit_price = targets[0]
                    exit_time = row['datetime']
                    break
        
        sig['outcome'] = outcome
        sig['win_type'] = win_type
        sig['exit_price'] = float(exit_price) if exit_price else None
        sig['exit_time'] = str(exit_time) if exit_time else None
        results.append(sig)
        candles_to_form_list.append(sig['candles_to_form_fvg_out'])
        
    # Calculate Stats by Speed Quality
    speed_stats = {}
    for sq in ['FAST', 'MEDIUM', 'SLOW', 'VERY_SLOW']:
        bucket = [r for r in results if r.get('speed_quality') == sq]
        if not bucket:
            speed_stats[sq] = {'total': 0, 'wins': 0, 'win_rate': 0.0}
            continue
        b_wins = [r for r in bucket if r['outcome'] == 'WIN']
        speed_stats[sq] = {
            'total': len(bucket),
            'wins': len(b_wins),
            'win_rate': round(len(b_wins) / len(bucket) * 100, 2)
        }

    wins_list = [r for r in results if r['outcome'] == 'WIN']
    losses_list = [r for r in results if r['outcome'] == 'LOSS']
    
    win_rate = (len(wins_list) / total_signals * 100) if total_signals > 0 else 0
    total_rr = sum([2.0 if r['outcome'] == 'WIN' else (-1.0 if r['outcome'] == 'LOSS' else 0.0) for r in results])
    
    summary = {
        'instrument': instrument,
        'timeframe': f"{context_tf}/{entry_tf}",
        'strategy': 'SHARP_TURN',
        'total_signals': total_signals,
        'wins': len(wins_list),
        'losses': len(losses_list),
        'neutrals': total_signals - len(wins_list) - len(losses_list),
        'win_rate_pct': round(win_rate, 2),
        'avg_rr': round(total_rr / total_signals, 2) if total_signals > 0 else 0,
        'total_rr': round(total_rr, 2),
        'avg_candles_to_fvg_out': round(float(np.mean(candles_to_form_list)), 2) if candles_to_form_list else 0,
        'win_rate_by_speed': speed_stats,
        'trades': results
    }
    
    return summary

def save_results(results, filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as f:
        json.dump(results, f, indent=4)
    print(f"Results saved to {filename}")

if __name__ == '__main__':
    res = run_backtest('EURUSD', 'DAILY', '1H')
    print(f"Backtest Complete | Signals: {res['total_signals']} | Win Rate: {res['win_rate_pct']}%")
    save_results(res, 'c:/Users/Admin/OneDrive/Desktop/MMC/mmc_backtest/backtest/results/s6_EURUSD_D_1H.json')

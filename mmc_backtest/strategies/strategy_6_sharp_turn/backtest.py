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
    
    for sig in signals:
        # Start simulation from sig_datetime
        sig_time = pd.to_datetime(sig['signal_datetime'])
        entry_price = sig['entry_price']
        stop_loss = sig['stop_loss']
        tp_2r = sig['tp_2r']
        context_target = sig['context_target']
        direction = sig['direction']
        
        # Get candles after signal
        trade_data = df_entry[df_entry['datetime'] > sig_time].head(100)
        
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
        
    wins = [r for r in results if r['outcome'] == 'WIN']
    losses = [r for r in results if r['outcome'] == 'LOSS']
    
    win_rate = (len(wins) / total_signals * 100) if total_signals > 0 else 0
    
    context_hits = [w for w in wins if w['win_type'] == 'CONTEXT']
    tp2r_hits = [w for w in wins if w['win_type'] == 'TP2R']
    
    context_hit_pct = (len(context_hits) / len(wins) * 100) if wins else 0
    tp2r_hit_pct = (len(tp2r_hits) / len(wins) * 100) if wins else 0
    
    summary = {
        'instrument': instrument,
        'context_tf': context_tf,
        'entry_tf': entry_tf,
        'total_signals': total_signals,
        'wins': len(wins),
        'losses': len(losses),
        'neutrals': total_signals - len(wins) - len(losses),
        'win_rate_pct': round(win_rate, 2),
        'avg_candles_to_form_fvg_out': round(float(np.mean(candles_to_form_list)), 2) if candles_to_form_list else 0,
        'context_target_hit_pct': round(context_hit_pct, 2),
        'tp2r_hit_pct': round(tp2r_hit_pct, 2),
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

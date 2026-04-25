import pandas as pd
import numpy as np
import os
import json
from collections import Counter
from modules.data_engine import fetch_candles
from strategies.strategy_7_order_flow_entry.scanner import scan_order_flow_entry

def run_backtest(instrument, context_tf, entry_tf, data_dir=None) -> dict:
    """
    Run Strategy 7 Backtest
    """
    print(f"Starting Strategy 7 Backtest for {instrument} {context_tf}/{entry_tf}...")
    
    df_context = fetch_candles(instrument, context_tf)
    df_entry = fetch_candles(instrument, entry_tf)
    
    if df_context is None or df_entry is None:
        return {"error": "Failed to load data"}
        
    signals = scan_order_flow_entry(df_context, df_entry, instrument, context_tf, entry_tf)
    
    results = []
    total_signals = len(signals)
    
    if total_signals == 0:
        return {'total_signals': 0, 'win_rate_pct': 0, 'trades': []}
        
    checklist_fails_counter = Counter()
    ofl_prob_pairs = []
    
    # 3. Build Datetime to Index mapping for fast lookup
    dt_to_idx = {str(dt): idx for idx, dt in enumerate(df_entry['datetime'])}
    
    for sig in signals:
        # Find signal index in df using optimized map
        sig_dt_str = str(sig['signal_datetime'])
        if sig_dt_str not in dt_to_idx:
            continue
        sig_idx = dt_to_idx[sig_dt_str]
        
        # Forward Simulation
        trade_data = df_entry.iloc[sig_idx + 1 : sig_idx + 101]
        
        direction = sig['direction']
        stop_loss = sig['stop_loss']
        tp_2r = sig['tp_2r']
        context_target = sig['context_target']
        
        outcome = 'NEUTRAL'
        win_type = None
        exit_price = None
        exit_time = None
        
        for _, row in trade_data.iterrows():
            # Stop Loss
            if direction == 'BULLISH':
                if row['low'] <= stop_loss:
                    outcome = 'LOSS'
                    exit_price = stop_loss
                    exit_time = row['datetime']
                    break
                
                targets = []
                if row['high'] >= tp_2r: targets.append(('TP2R', tp_2r))
                if row['high'] >= context_target: targets.append(('CONTEXT', context_target))
                
                if targets:
                    outcome = 'WIN'
                    targets.sort(key=lambda x: x[1])
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
                    targets.sort(key=lambda x: x[1], reverse=True)
                    win_type, exit_price = targets[0]
                    exit_time = row['datetime']
                    break
                    
        sig['outcome'] = outcome
        sig['win_type'] = win_type
        sig['exit_price'] = float(exit_price) if exit_price else None
        sig['exit_time'] = str(exit_time) if exit_time else None
        results.append(sig)

    wins_list = [r for r in results if r['outcome'] == 'WIN']
    losses_list = [r for r in results if r['outcome'] == 'LOSS']
    neutrals_count = total_signals - len(wins_list) - len(losses_list)
    
    total_rr = sum([2.0 if r['outcome'] == 'WIN' else (-1.0 if r['outcome'] == 'LOSS' else 0.0) for r in results])
    
    # Extra stats
    fully_passed = [s for s in signals if not s['checklist_failed_items'] and not s['checklist_warn_items']]
    most_common_fail = checklist_fails_counter.most_common(1)[0][0] if checklist_fails_counter else "None"
    
    summary = {
        'instrument': instrument,
        'timeframe': f"{context_tf}/{entry_tf}",
        'strategy': 'ORDER_FLOW_ENTRY',
        'total_signals': total_signals,
        'wins': len(wins_list),
        'losses': len(losses_list),
        'neutrals': neutrals_count,
        'win_rate_pct': round(len(wins_list) / total_signals * 100, 2) if total_signals > 0 else 0,
        'avg_rr': round(total_rr / total_signals, 2) if total_signals > 0 else 0,
        'total_rr': round(total_rr, 2),
        'fully_checklist_passed_pct': round(len(fully_passed) / total_signals * 100, 2) if total_signals > 0 else 0,
        'most_common_checklist_fail': most_common_fail,
        'ofl_probability_breakdown': dict(Counter(ofl_prob_pairs)),
        'trades': results
    }
    
    return summary

def save_results(results, filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as f:
        json.dump(results, f, indent=4)
    print(f"Results saved to {filename}")

if __name__ == '__main__':
    res = run_backtest('EURUSD', 'DAILY', '15M')
    print(f"Backtest Complete | Signals: {res.get('total_signals', 0)} | Win Rate: {res.get('win_rate_pct', 0)}%")
    if 'total_signals' in res:
        save_results(res, 'c:/Users/Admin/OneDrive/Desktop/MMC/mmc_backtest/backtest/results/s7_EURUSD_D_15M.json')

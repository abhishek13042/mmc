import sys
import os
import json
import pandas as pd
from datetime import datetime

# Add project root and mmc_backtest folder to path for imports to work
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
MMC_DIR = os.path.join(ROOT_DIR, 'mmc_backtest')
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, MMC_DIR)

from mmc_backtest.backtest.data_loader import fetch_candles
from mmc_backtest.strategies.strategy_3_liquidity_sweep.scanner import scan_liquidity_sweep

def run_backtest(instrument, timeframe, data_dir=None):
    """
    Full backtest runner for Strategy 3: Liquidity Sweep Reversal.
    """
    print(f"Starting Strategy 3 Backtest: {instrument} {timeframe}")
    
    try:
        df = fetch_candles(instrument, timeframe, data_dir)
        print(f"Loaded {len(df)} candles.")
    except Exception as e:
        print(f"Error loading data: {e}")
        return None
        
    print("Scanning for Sweep Signals...")
    signals = scan_liquidity_sweep(df, instrument, timeframe)
    print(f"Found {len(signals)} signals.")
    
    if not signals:
        return {
            "instrument": instrument, "timeframe": timeframe, "total_signals": 0, "trades": [],
            "stats": {"total_signals": 0, "wins": 0, "losses": 0, "win_rate_pct": 0, "total_rr": 0}
        }
        
    trades = []
    for sig in signals:
        signal_dt = sig['signal_datetime']
        idx_list = df.index[df['datetime'] == signal_dt].tolist()
        if not idx_list: continue
        
        start_idx = idx_list[0] + 1
        direction = sig['direction']
        entry = sig['entry_price']
        sl = sig['stop_loss']
        tp = sig['tp_target']
        
        outcome = {
            'signal_datetime': signal_dt,
            'direction': direction,
            'entry_price': entry,
            'stop_loss': sl,
            'tp_target': tp,
            'result': 'PENDING',
            'rr_achieved': 0.0,
            'exit_datetime': None,
            'candles_held': 0,
            'risk_pips': sig['risk_pips']
        }
        
        # Risk amount
        risk_dist = abs(entry - sl)
        target_rr = abs(tp - entry) / risk_dist if risk_dist > 0 else 0
        
        # Max hold: 50 candles (sweeps are fast reversals)
        for j in range(start_idx, min(start_idx + 50, len(df))):
            curr_candle = df.iloc[j]
            outcome['candles_held'] += 1
            
            if direction == 'BULLISH':
                if curr_candle['low'] <= sl:
                    outcome['result'] = 'LOSS'; outcome['rr_achieved'] = -1.0
                    outcome['exit_datetime'] = curr_candle['datetime']
                    break
                if curr_candle['high'] >= tp:
                    outcome['result'] = 'WIN'; outcome['rr_achieved'] = round(target_rr, 2)
                    outcome['exit_datetime'] = curr_candle['datetime']
                    break
            else: # BEARISH
                if curr_candle['high'] >= sl:
                    outcome['result'] = 'LOSS'; outcome['rr_achieved'] = -1.0
                    outcome['exit_datetime'] = curr_candle['datetime']
                    break
                if curr_candle['low'] <= tp:
                    outcome['result'] = 'WIN'; outcome['rr_achieved'] = round(target_rr, 2)
                    outcome['exit_datetime'] = curr_candle['datetime']
                    break
                    
        if outcome['result'] == 'PENDING':
            outcome['result'] = 'NEUTRAL'; outcome['rr_achieved'] = 0.0
            
        trades.append(outcome)
        
    stats = calculate_performance(trades)
    results = {
        "instrument": instrument, "timeframe": timeframe, "strategy": "LIQUIDITY_SWEEP",
        "generated_at": datetime.now().isoformat(), "stats": stats, "trades": trades
    }
    return results

def calculate_performance(trades):
    if not trades: return {}
    wins = [t for t in trades if t['result'] == 'WIN']
    losses = [t for t in trades if t['result'] == 'LOSS']
    total_comp = len(wins) + len(losses)
    win_rate = (len(wins) / total_comp * 100) if total_comp > 0 else 0
    total_rr = sum(t['rr_achieved'] for t in trades)
    
    return {
        "total_signals": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate_pct": round(win_rate, 2), "total_rr": round(total_rr, 2),
        "avg_rr": round(total_rr / len(trades), 2) if trades else 0
    }

def save_results(results, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to: {output_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='MMC Strategy 3 Backtest')
    parser.add_argument('--instrument', type=str, default='EURUSD')
    parser.add_argument('--timeframe', type=str, default='DAILY')
    args = parser.parse_args()
    
    results = run_backtest(args.instrument, args.timeframe)
    if results:
        print("\n--- Strategy 3 Results ---")
        for k, v in results['stats'].items(): print(f"{k}: {v}")
        output_file = os.path.join(os.path.dirname(__file__), f'../../backtest/results/strategy_3_{args.instrument.lower()}_{args.timeframe.lower()}.json')
        save_results(results, output_file)

import sys, os
import pandas as pd
import numpy as np
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../../..')))

from mmc_backtest.backtest.data_loader import fetch_candles
from mmc_backtest.strategies.strategy_8_it_retracement.scanner import scan_it_retracement

def run_backtest(instrument, timeframe, data_dir=None) -> dict:
    """
    Run full historical backtest for Strategy 8.
    Returns flat result dict matching MASTER_SUMMARY standard.
    """
    print(f"Starting Strategy 8 Backtest: {instrument} {timeframe}")
    
    df = fetch_candles(instrument, timeframe, data_dir)
    if df is None or df.empty:
        return {"error": f"No data for {instrument} {timeframe}"}
        
    signals = scan_it_retracement(df, instrument, timeframe)

    # 3. Build Datetime to Index mapping for fast lookup
    dt_to_idx = {str(dt): idx for idx, dt in enumerate(df['datetime'])}
    
    trades = []
    for sig in signals:
        # Find signal index in df using optimized map
        sig_dt_str = str(sig['signal_datetime'])
        if sig_dt_str not in dt_to_idx:
            continue
        sig_idx = dt_to_idx[sig_dt_str]
            
        result      = 'NEUTRAL'
        rr_achieved = 0.0
        exit_price  = None
        exit_time   = None

        # Simulate walking forward 100 candles
        for k in range(sig_idx + 1, min(sig_idx + 101, len(df))):
            candle = df.iloc[k]
            if sig['direction'] == 'BULLISH':
                # Stop Loss check
                if candle['low'] <= sig['stop_loss']:
                    result = 'LOSS'
                    rr_achieved = -1.0
                    exit_price = sig['stop_loss']
                    exit_time = candle['datetime']
                    break
                # TP Target check
                if candle['high'] >= sig['tp_2r']:
                    result = 'WIN'
                    rr_achieved = 2.0
                    exit_price = sig['tp_2r']
                    exit_time = candle['datetime']
                    
                    # Check if tp_4r hit in same or later candles
                    # For simplicity, if tp_4r is reached before SL, we take the better RR
                    if candle['high'] >= sig['tp_4r']:
                        rr_achieved = round(abs(sig['tp_4r'] - sig['entry_price']) / abs(sig['entry_price'] - sig['stop_loss']), 2)
                        exit_price = sig['tp_4r']
                    break
            else: # BEARISH
                # Stop Loss check
                if candle['high'] >= sig['stop_loss']:
                    result = 'LOSS'
                    rr_achieved = -1.0
                    exit_price = sig['stop_loss']
                    exit_time = candle['datetime']
                    break
                # TP Target check
                if candle['low'] <= sig['tp_2r']:
                    result = 'WIN'
                    rr_achieved = 2.0
                    exit_price = sig['tp_2r']
                    exit_time = candle['datetime']
                    
                    if candle['low'] <= sig['tp_4r']:
                        rr_achieved = round(abs(sig['tp_4r'] - sig['entry_price']) / abs(sig['entry_price'] - sig['stop_loss']), 2)
                        exit_price = sig['tp_4r']
                    break

        trades.append({
            **sig,
            'result': result,
            'rr_achieved': rr_achieved,
            'exit_price': round(float(exit_price), 5) if exit_price else None,
            'exit_datetime': str(exit_time) if exit_time else None
        })

    wins     = sum(1 for t in trades if t['result'] == 'WIN')
    losses   = sum(1 for t in trades if t['result'] == 'LOSS')
    neutrals = sum(1 for t in trades if t['result'] == 'NEUTRAL')
    total    = len(trades)
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0
    
    total_rr = sum(t['rr_achieved'] for t in trades)
    avg_rr   = total_rr / total if total > 0 else 0.0

    # Extra stats specific to S8
    if trades:
        avg_candles = sum(t.get('candles_since_break', 0) for t in trades) / len(trades)
        fast_trades = [t for t in trades if t.get('candles_since_break', 99) <= 5]
        fast_wr     = (sum(1 for t in fast_trades if t['result'] == 'WIN') / 
                       len(fast_trades) * 100) if fast_trades else 0.0
    else:
        avg_candles = 0.0
        fast_wr     = 0.0

    print(f"\nS8 IT_RETRACEMENT | {instrument} {timeframe}")
    print(f"Signals: {total} | Wins: {wins} | Losses: {losses} | WR: {win_rate:.1f}%")
    print(f"Avg RR: {avg_rr:.2f} | Total RR: {total_rr:.2f}")
    print(f"Avg candles to entry: {avg_candles:.1f} | Fast entry WR: {fast_wr:.1f}%")

    return {
        'instrument':    instrument,
        'timeframe':     timeframe,
        'strategy':      'IT_RETRACEMENT',
        'total_signals': total,
        'wins':          wins,
        'losses':        losses,
        'neutrals':      neutrals,
        'win_rate_pct':  round(win_rate, 2),
        'avg_rr':        round(avg_rr, 2),
        'total_rr':      round(total_rr, 2),
        'avg_candles_to_entry': round(avg_candles, 1),
        'fast_entry_win_rate':  round(fast_wr, 2),
        'trades':        trades
    }

if __name__ == "__main__":
    res = run_backtest('EURUSD', '1H')
    if 'error' not in res:
        print(f"Backtest success. signals: {res['total_signals']}")

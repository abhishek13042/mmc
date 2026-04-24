import sys, os
import pandas as pd
import numpy as np
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../../..')))

from mmc_backtest.backtest.data_loader import fetch_candles
from mmc_backtest.strategies.strategy_9_pch_pcl_sweep.scanner import scan_pch_pcl_sweep

def run_backtest(instrument, timeframe, data_dir=None) -> dict:
    """Standard walk-forward simulation for S9."""
    print(f"Starting Strategy 9 Backtest: {instrument} {timeframe}")
    
    df = fetch_candles(instrument, timeframe, data_dir)
    if df is None or df.empty:
        return {"error": f"No data for {instrument} {timeframe}"}
        
    signals = scan_pch_pcl_sweep(df, instrument, timeframe)
    trades  = []

    for sig in signals:
        try:
            # Find signal index in df
            sig_dt = pd.to_datetime(sig['signal_datetime'])
            if sig_dt in df['datetime'].values:
                sig_idx = df.index[df['datetime'] == sig_dt][0]
            else:
                diffs = (pd.to_datetime(df['datetime']) - sig_dt).abs()
                sig_idx = diffs.idxmin()
        except Exception:
            continue

        result = 'NEUTRAL'
        rr_achieved = 0.0
        exit_price = None
        exit_time = None

        # Entry happens at sig_idx + 1 (the sweep candle close)
        # Simulation starts from sig_idx + 2
        for k in range(sig_idx + 2, min(sig_idx + 101, len(df))):
            candle = df.iloc[k]
            if sig['direction'] == 'BULLISH':
                if candle['low'] <= sig['stop_loss']:
                    result = 'LOSS'
                    rr_achieved = -1.0
                    exit_price = sig['stop_loss']
                    exit_time = candle['datetime']
                    break
                if candle['high'] >= sig['tp_2r']:
                    result = 'WIN'
                    rr_achieved = 2.0
                    exit_price = sig['tp_2r']
                    exit_time = candle['datetime']
                    if candle['high'] >= sig['tp_4r']:
                        rr_achieved = round(abs(sig['tp_4r'] - sig['entry_price']) / abs(sig['entry_price'] - sig['stop_loss']), 2)
                        exit_price = sig['tp_4r']
                    break
            else:
                if candle['high'] >= sig['stop_loss']:
                    result = 'LOSS'
                    rr_achieved = -1.0
                    exit_price = sig['stop_loss']
                    exit_time = candle['datetime']
                    break
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

    # PCH vs PCL breakdown
    pch = [t for t in trades if t.get('sweep_type') == 'PCH']
    pcl = [t for t in trades if t.get('sweep_type') == 'PCL']
    pch_wr = (sum(1 for t in pch if t['result'] == 'WIN')
               / (sum(1 for t in pch if t['result'] in ['WIN', 'LOSS'])) * 100) if any(t['result'] in ['WIN', 'LOSS'] for t in pch) else 0.0
    pcl_wr = (sum(1 for t in pcl if t['result'] == 'WIN')
               / (sum(1 for t in pcl if t['result'] in ['WIN', 'LOSS'])) * 100) if any(t['result'] in ['WIN', 'LOSS'] for t in pcl) else 0.0

    print(f"\nS9 PCH_PCL_SWEEP | {instrument} {timeframe}")
    print(f"Signals: {total} | Wins: {wins} | Losses: {losses} | WR: {win_rate:.1f}%")
    print(f"PCH: {len(pch)} trades, WR: {pch_wr:.1f}% | PCL: {len(pcl)} trades, WR: {pcl_wr:.1f}%")
    print(f"Avg RR: {avg_rr:.2f} | Total RR: {total_rr:.2f}")

    return {
        'instrument':    instrument,
        'timeframe':     timeframe,
        'strategy':      'PCH_PCL_SWEEP',
        'total_signals': total,
        'wins':          wins,
        'losses':        losses,
        'neutrals':      neutrals,
        'win_rate_pct':  round(win_rate, 2),
        'avg_rr':        round(avg_rr, 2),
        'total_rr':      round(total_rr, 2),
        'pch_win_rate':  round(pch_wr, 2),
        'pcl_win_rate':  round(pcl_wr, 2),
        'trades':        trades
    }

if __name__ == "__main__":
    res = run_backtest('EURUSD', '1H')
    if 'error' not in res:
        print(f"Backtest success. signals: {res['total_signals']}")

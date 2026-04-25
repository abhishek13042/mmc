import os
import sys
import pandas as pd
import numpy as np

# Setup paths for imports
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
MMC_DIR = os.path.join(ROOT_DIR, 'mmc_backtest')
if ROOT_DIR not in sys.path: sys.path.insert(0, ROOT_DIR)
if MMC_DIR not in sys.path: sys.path.insert(0, MMC_DIR)

from modules.data_engine import fetch_candles
from modules.video1_pd_arrays import scan_candles_for_fvgs, scan_candles_for_swings, get_pip_multiplier
from modules.video3_4_order_flow import scan_candles_for_ofls
from modules.video8_sweeps import analyze_sweep, classify_liquidity_event

def scan_sweep_ofl(df, instrument, timeframe):
    """
    SUPER-OPTIMIZED Strategy 4 Scanner (O(N)).
    """
    signals = []
    pip_multiplier = get_pip_multiplier(instrument)
    
    # 1. Pre-calculate all indicators
    all_swings = scan_candles_for_swings(df)
    all_fvgs = sorted(scan_candles_for_fvgs(df, instrument), key=lambda x: x['candle3_datetime'])
    all_ofls = sorted(scan_candles_for_ofls(df, instrument), key=lambda x: x['datetime'])
    
    # 2. Map FVGs to candles for O(1) lookup
    fvg_lookup = {}
    for f in all_fvgs:
        dt = f['candle3_datetime']
        if dt not in fvg_lookup: fvg_lookup[dt] = []
        fvg_lookup[dt].append(f)

    # 3. Pointers
    ofl_ptr = 0
    current_ofl = None
    
    min_wick_pips = 20.0 if 'XAU' in instrument else 2.0

    for i in range(50, len(df)):
        current_candle = df.iloc[i]
        curr_dt = current_candle['datetime']
        
        # Update OFL Pointer
        while ofl_ptr < len(all_ofls) and all_ofls[ofl_ptr]['datetime'] <= curr_dt:
            current_ofl = all_ofls[ofl_ptr]
            ofl_ptr += 1
            
        if not current_ofl or current_ofl['probability_label'] not in ['HIGH', 'MEDIUM']:
            continue
            
        # 1. Condition 1: Clean Sweep Event at current candle
        sweep_res = analyze_sweep(instrument, timeframe, i, df, all_swings, [])
        if not sweep_res or sweep_res['liquidity_event'] != 'SWEEP' or sweep_res['comfortable_candles'] > 1 or sweep_res['wick_size_pips'] < min_wick_pips or sweep_res['is_aggressive']:
            continue
            
        direction = sweep_res['sweep_direction']
        if direction != current_ofl['direction']:
            continue
            
        # 2. Condition 2: Continuation FVG forms after sweep (within 5 candles)
        found_cont_fvg = None
        for j in range(i + 1, min(i + 6, len(df))):
            check_dt = df.iloc[j]['datetime']
            if check_dt in fvg_lookup:
                for fvg in fvg_lookup[check_dt]:
                    if fvg['direction'] == direction and fvg['fvg_type'] in ['PFVG', 'BFVG']:
                        found_cont_fvg = fvg
                        break
            if found_cont_fvg: break
            
        if not found_cont_fvg:
            continue
            
        # Entry & SL
        entry_price = found_cont_fvg['fvg_low'] if direction == 'BULLISH' else found_cont_fvg['fvg_high']
        sl = current_ofl['swing_point_price']
        risk = abs(entry_price - sl)
        if risk <= 0: continue
        
        tp_2r = entry_price + (risk * 2.0) if direction == 'BULLISH' else entry_price - (risk * 2.0)
        tp_4r = entry_price + (risk * 4.0) if direction == 'BULLISH' else entry_price - (risk * 4.0)
        
        # Optimized Structural Target Lookback
        search_swings = all_swings[-200:] # Limit structural lookback
        highs = [s['swing_level'] for s in search_swings if s['swing_type'] == 'SWING_HIGH' and s['swing_level'] > entry_price and s['datetime'] < curr_dt]
        lows = [s['swing_level'] for s in search_swings if s['swing_type'] == 'SWING_LOW' and s['swing_level'] < entry_price and s['datetime'] < curr_dt]
        
        target_price = None
        if direction == 'BULLISH':
            target_price = min(highs) if highs else tp_4r
        else:
            target_price = max(lows) if lows else tp_4r
            
        final_tp = min(target_price, tp_4r) if direction == 'BULLISH' else max(target_price, tp_4r)
        if (direction == 'BULLISH' and final_tp < tp_2r) or (direction == 'BEARISH' and final_tp > tp_2r):
            continue
            
        signals.append({
            'strategy': 'SWEEP_OFL',
            'instrument': instrument,
            'timeframe': timeframe,
            'signal_datetime': curr_dt,
            'direction': direction,
            'entry_price': round(entry_price, 5),
            'stop_loss': round(sl, 5),
            'tp_2r': round(tp_2r, 5),
            'tp_4r': round(final_tp, 5),
            'risk_pips': round(risk * pip_multiplier, 2)
        })
        
    return signals
        
    return signals

if __name__ == "__main__":
    try:
        df = fetch_candles('EURUSD', '1H')
        if df is not None and not df.empty:
            # For testing, scan last 500 candles
            test_df = df.tail(500).copy()
            signals = scan_sweep_ofl(test_df, 'EURUSD', '1H')
            print(f"Scanner OK | Sweep+OFL Signals: {len(signals)}")
            if signals:
                print(f"First Signal: {signals[0]['signal_datetime']} | Direction: {signals[0]['direction']}")
        else:
            print("No data found for EURUSD 1H")
    except Exception as e:
        print(f"Error in scanner: {e}")

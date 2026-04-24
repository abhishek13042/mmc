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
    Scans for Sweep + OFL setups based on:
    - Clean Liquidity Sweep (Comfortable candles <= 1)
    - Continuation FVG (PFVG/BFVG)
    - Aligned Order Flow (HIGH/MEDIUM probability)
    """
    signals = []
    pip_multiplier = get_pip_multiplier(instrument)
    
    # Buffers
    if 'JPY' in instrument:
        buffer = 0.02
    elif 'XAU' in instrument:
        buffer = 0.20
    else:
        buffer = 0.0002
        
    min_wick_pips = 20.0 if 'XAU' in instrument else 2.0

    # Scan for swings and FVGs once for efficiency
    all_swings = scan_candles_for_swings(df)
    
    # Iterate through candles
    for i in range(50, len(df)):
        current_candle = df.iloc[i]
        current_time = current_candle['datetime']
        
        # 1. Condition 1: Clean Sweep Event
        # analyze_sweep checks the candle at 'i' against all previous swings
        sweep_res = analyze_sweep(instrument, timeframe, i, df, all_swings, [])
        
        if not sweep_res:
            continue
            
        # Validate sweep criteria
        if sweep_res['liquidity_event'] != 'SWEEP':
            continue
        if sweep_res['comfortable_candles'] > 1:
            continue
        if sweep_res['wick_size_pips'] < min_wick_pips:
            continue
        if sweep_res['is_aggressive']:
            continue
            
        direction = sweep_res['sweep_direction']
        swept_level = sweep_res['swept_level']
        
        # 2. Condition 2: Continuation FVG Forms After Sweep (1-5 candles)
        # analyze_sweep already checks for continuation FVG in the next 5 candles
        cont_fvg_high = sweep_res.get('continuation_fvg_high')
        cont_fvg_low = sweep_res.get('continuation_fvg_low')
        
        if cont_fvg_high is None or cont_fvg_low is None:
            continue
            
        # We need to find the actual FVG object to check its type
        # scan next 5 candles
        next_5 = df.iloc[i+1 : i+6]
        found_fvgs = scan_candles_for_fvgs(next_5, instrument)
        cont_fvg = next((f for f in found_fvgs if f['direction'] == direction), None)
        
        if not cont_fvg or cont_fvg['fvg_type'] not in ['PFVG', 'BFVG']:
            continue
            
        # 3. Condition 3: OFL Present and Aligned
        window = df.iloc[:i+1]
        ofls = scan_candles_for_ofls(window, instrument)
        matching_ofls = [
            o for o in ofls 
            if o['direction'] == direction and 
            o['probability_label'] in ['HIGH', 'MEDIUM']
        ]
        
        if not matching_ofls:
            continue
            
        # ENTRY PRICE
        # BULLISH sweep: entry = continuation_fvg['fvg_low']
        # BEARISH sweep: entry = continuation_fvg['fvg_high']
        entry_price = cont_fvg['fvg_low'] if direction == 'BULLISH' else cont_fvg['fvg_high']
        
        # STOP LOSS: most recent OFL swing point price
        sl = matching_ofls[-1]['swing_point_price']
        
        risk = abs(entry_price - sl)
        if risk <= 0: continue
        
        tp_2r = entry_price + (risk * 2.0) if direction == 'BULLISH' else entry_price - (risk * 2.0)
        tp_4r = entry_price + (risk * 4.0) if direction == 'BULLISH' else entry_price - (risk * 4.0)
        
        # 4. Take Profit: Nearest opposing swing (BSL/SSL)
        # BSL: nearest swing high ABOVE entry for bullish
        # SSL: nearest swing low BELOW entry for bearish
        target_price = None
        target_type = None
        
        if direction == 'BULLISH':
            # Find closest swing high above entry
            highs = [s['swing_level'] for s in all_swings if s['swing_type'] == 'SWING_HIGH' and s['swing_level'] > entry_price]
            if highs:
                target_price = min(highs)
                target_type = 'BSL'
        else:
            lows = [s['swing_level'] for s in all_swings if s['swing_type'] == 'SWING_LOW' and s['swing_level'] < entry_price]
            if lows:
                target_price = max(lows)
                target_type = 'SSL'
                
        if not target_price:
            target_price = tp_4r
            target_type = 'RR_TARGET'
            
        # Validate TP: must be at least 2R
        if direction == 'BULLISH':
            final_tp = min(target_price, tp_4r)
            if final_tp < tp_2r: continue
        else:
            final_tp = max(target_price, tp_4r)
            if final_tp > tp_2r: continue
            
        signals.append({
            'strategy': 'SWEEP_OFL',
            'instrument': instrument,
            'timeframe': timeframe,
            'signal_datetime': current_time,
            'direction': direction,
            'entry_price': round(entry_price, 5),
            'stop_loss': round(sl, 5),
            'tp_2r': round(tp_2r, 5),
            'tp_4r': round(final_tp, 5),
            'risk_pips': round(risk * pip_multiplier, 2),
            'swept_level': round(swept_level, 5),
            'sweep_wick_pips': sweep_res['wick_size_pips'],
            'comfortable_candles': sweep_res['comfortable_candles'],
            'continuation_fvg_high': round(cont_fvg['fvg_high'], 5),
            'continuation_fvg_low': round(cont_fvg['fvg_low'], 5),
            'continuation_fvg_type': cont_fvg['fvg_type'],
            'ofl_probability': matching_ofls[-1]['probability_label'],
            'structural_target': round(target_price, 5),
            'structural_target_type': target_type,
            'sweep_probability_score': sweep_res['probability_score'],
            'conditions_met': ['SWEEP', 'CONT_FVG', 'OFL_CONFIRM'],
        })
        
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

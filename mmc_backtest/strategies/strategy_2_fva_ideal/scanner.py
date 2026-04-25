import sys
import os
import pandas as pd
import json
from collections import defaultdict

# Add project root and mmc_backtest folder to path for imports to work
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
MMC_DIR = os.path.join(ROOT_DIR, 'mmc_backtest')
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, MMC_DIR)

from mmc_backtest.modules.video1_pd_arrays import (
    scan_candles_for_fvgs, 
    scan_candles_for_swings, 
    get_pip_multiplier,
    check_mitigation
)
from mmc_backtest.modules.video2_market_structure import (
    scan_it_points,
    build_fva_from_it_points
)
from mmc_backtest.modules.video3_4_order_flow import scan_candles_for_ofls
from mmc_backtest.backtest.data_loader import fetch_candles

def scan_fva_ideal(df, instrument, timeframe):
    """
    SUPER-OPTIMIZED Strategy 2 Scanner.
    $O(N)$ linear complexity using sequential pointers.
    """
    signals = []
    pip_multiplier = get_pip_multiplier(instrument)
    
    # Buffer: EURUSD/GBPUSD=0.0002, XAUUSD=0.20
    buffer = 0.20 if instrument == "XAUUSD" else 0.0002
    
    print(f"Pre-calculating Indicators for {timeframe}...")
    all_fvgs = scan_candles_for_fvgs(df, instrument)
    all_it_points = sorted(scan_it_points(df), key=lambda x: x['datetime'])
    all_ofls = sorted(scan_candles_for_ofls(df, instrument), key=lambda x: x['datetime'])

    # Index mappings for fast lookup
    fvg_by_dt = defaultdict(list)
    for f in all_fvgs:
        fvg_by_dt[f['candle3_datetime']].append(f)
        
    it_highs = [p for p in all_it_points if p['point_type'] == 'IT_HIGH']
    it_lows = [p for p in all_it_points if p['point_type'] == 'IT_LOW']
    
    # Pointers
    ofl_ptr = 0
    high_ptr = 0
    low_ptr = 0
    
    visible_fvgs = []
    current_ofl = None
    recent_it_high = None
    recent_it_low = None

    print(f"Scanning {len(df)} candles for FVA Ideal setups...")
    for i in range(50, len(df)):
        current_candle = df.iloc[i]
        curr_dt = current_candle['datetime']
        curr_close = current_candle['close']
        
        # 1. Update Indicators using Pointers
        while ofl_ptr < len(all_ofls) and all_ofls[ofl_ptr]['datetime'] <= curr_dt:
            current_ofl = all_ofls[ofl_ptr]; ofl_ptr += 1
            
        while high_ptr < len(it_highs) and it_highs[high_ptr]['datetime'] <= curr_dt:
            recent_it_high = it_highs[high_ptr]; high_ptr += 1
            
        while low_ptr < len(it_lows) and it_lows[low_ptr]['datetime'] <= curr_dt:
            recent_it_low = it_lows[low_ptr]; low_ptr += 1

        # Accumulate FVGs seen so far (optional, we mainly need overlapping ones)
        # For S2, we only care about FVGs that overlap the FVA boundary.
        
        if not recent_it_high or not recent_it_low or not current_ofl:
            continue
            
        if recent_it_high['price_level'] <= recent_it_low['price_level']:
            continue
            
        # 2. Build FVA from current IT context
        # build_fva_from_it_points is fast if we pass relevant FVG list
        # We only need FVGs near the current boundary. 
        # For simplicity, we'll use all_fvgs but ideally we filter.
        fva = build_fva_from_it_points(
            recent_it_high['price_level'], 
            recent_it_low['price_level'], 
            instrument, 
            all_fvgs, 
            all_it_points
        )
        
        if fva['fva_type'] != 'IDEAL' or not fva['has_overlapping_fvg'] or not fva['has_nested_fva'] or fva['is_sweep']:
            continue
            
        fva_high = fva['fva_high']
        fva_low = fva['fva_low']
        
        # 3. Proximity Check
        direction = None
        is_bullish_test = (fva_low <= curr_close <= fva_low + (5 / pip_multiplier)) and (curr_close > fva_low - buffer)
        is_bearish_test = (fva_high - (5 / pip_multiplier) <= curr_close <= fva_high) and (curr_close < fva_high + buffer)
        
        if is_bullish_test: direction = 'BULLISH'
        elif is_bearish_test: direction = 'BEARISH'
        else: continue
            
        # 4. OFL Check
        # OFL must exist within the FVA zone and match direction
        if current_ofl['direction'] == direction and \
           fva_low <= current_ofl['swing_point_price'] <= fva_high and \
           current_ofl['probability_label'] in ['HIGH', 'MEDIUM']:
            
            # Setup Entry/SL/TP
            if direction == 'BULLISH':
                entry_price = fva['nested_fva_low'] or fva_low
                stop_loss = current_ofl['swing_point_price']
                structural_target = recent_it_high['price_level']
            else:
                entry_price = fva['nested_fva_high'] or fva_high
                stop_loss = current_ofl['swing_point_price']
                structural_target = recent_it_low['price_level']
                
            risk = abs(entry_price - stop_loss)
            if risk <= 0: continue
                
            tp_2r = entry_price + (risk * 2.0) if direction == 'BULLISH' else entry_price - (risk * 2.0)
            tp_4r = entry_price + (risk * 4.0) if direction == 'BULLISH' else entry_price - (risk * 4.0)
            
            # Logic for choosing target: Structural vs 4R
            use_target = structural_target if abs(structural_target - entry_price) < abs(tp_4r - entry_price) else tp_4r
            
            # Skip if reward to structural target < 2R
            if abs(use_target - entry_price) < abs(tp_2r - entry_price):
                continue
                
            signals.append({
                'strategy': 'FVA_IDEAL',
                'instrument': instrument,
                'timeframe': timeframe,
                'signal_datetime': curr_dt,
                'direction': direction,
                'entry_price': round(entry_price, 5),
                'stop_loss': round(stop_loss, 5),
                'tp_2r': round(tp_2r, 5),
                'tp_4r': round(use_target, 5),
                'risk_pips': round(risk * pip_multiplier, 2),
                'fva_high': round(fva_high, 5),
                'fva_low': round(fva_low, 5),
                'nested_fva_high': round(fva['nested_fva_high'], 5) if fva['nested_fva_high'] else None,
                'nested_fva_low': round(fva['nested_fva_low'], 5) if fva['nested_fva_low'] else None,
                'structural_target': round(structural_target, 5),
                'ofl_probability': current_ofl['probability_label'],
                'conditions_met': ['IDEAL_FVA', 'PROXIMITY', 'OFL_PRESENT']
            })
            
    return signals

if __name__ == '__main__':
    # Test with EURUSD 1H
    try:
        df = fetch_candles('EURUSD', '1H')
        if df is not None and not df.empty:
            # Scan only last 500 candles for test speed
            test_df = df.tail(500).copy()
            signals = scan_fva_ideal(test_df, 'EURUSD', '1H')
            print(f"Scanner OK | FVA Ideal Signals: {len(signals)}")
            if signals:
                print(f"First Signal: {signals[0]['signal_datetime']} | Direction: {signals[0]['direction']}")
        else:
            print("No data found for EURUSD 1H")
    except Exception as e:
        print(f"Error in scanner: {e}")

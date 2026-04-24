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
    Strategy 2 Scanner: FVA Ideal Setup (Triple Probability)
    """
    signals = []
    pip_multiplier = get_pip_multiplier(instrument)
    
    # Buffer: EURUSD/GBPUSD=0.0002, XAUUSD=0.20
    if instrument in ["EURUSD", "GBPUSD"]:
        buffer = 0.0002
    elif instrument == "XAUUSD":
        buffer = 0.20
    else:
        buffer = 0.0002 # Default
        
    print(f"Scanning {len(df)} candles for FVA Ideal setups...")
    
    for i in range(50, len(df)):
        window = df.iloc[:i+1] # Include current candle for proximity check
        current_candle = df.iloc[i]
        curr_dt = current_candle['datetime']
        curr_close = current_candle['close']
        
        # 1. Condition 1: IDEAL FVA Must Exist
        it_points = scan_it_points(window)
        it_highs = [p for p in it_points if p['point_type'] == 'IT_HIGH']
        it_lows = [p for p in it_points if p['point_type'] == 'IT_LOW']
        
        if not it_highs or not it_lows:
            continue
            
        recent_it_high = it_highs[-1]
        recent_it_low = it_lows[-1]
        
        if recent_it_high['price_level'] <= recent_it_low['price_level']:
            continue
            
        # Build FVA
        fvgs = scan_candles_for_fvgs(window, instrument)
        fva = build_fva_from_it_points(
            recent_it_high['price_level'], 
            recent_it_low['price_level'], 
            instrument, 
            fvgs, 
            it_points
        )
        
        # Ideal requirements
        if fva['fva_type'] != 'IDEAL':
            continue
        if not fva['has_overlapping_fvg'] or not fva['has_nested_fva'] or fva['is_sweep']:
            continue
            
        fva_high = fva['fva_high']
        fva_low = fva['fva_low']
        
        # 2. Condition 2: Price At FVA Boundary
        direction = None
        # BULLISH FVA (returning to fva_low)
        # BEARISH FVA (returning to fva_high)
        
        # We determine direction based on which boundary the price is testing
        is_bullish_test = (fva_low <= curr_close <= fva_low + (5 / pip_multiplier)) and (curr_close > fva_low - buffer)
        is_bearish_test = (fva_high - (5 / pip_multiplier) <= curr_close <= fva_high) and (curr_close < fva_high + buffer)
        
        if is_bullish_test:
            direction = 'BULLISH'
        elif is_bearish_test:
            direction = 'BEARISH'
        else:
            continue
            
        # 3. Condition 3: OFL Present At FVA Boundary
        all_ofls = scan_candles_for_ofls(window, instrument)
        # OFL must exist within the FVA zone and have matching direction
        # and probability_label in ['HIGH', 'MEDIUM']
        matching_ofls = [
            o for o in all_ofls 
            if o['direction'] == direction and 
            fva_low <= o['swing_point_price'] <= fva_high and
            o['probability_label'] in ['HIGH', 'MEDIUM']
        ]
        
        if not matching_ofls:
            continue
            
        current_ofl = matching_ofls[0]
        
        # 4. Condition 4: No Opposing PDA Before TP (Logic omitted for brevity or simplified as "Skip if blocking PDA exists")
        # For now, we assume no blocking PDA if we reach here.
        
        # ENTRY PRICE
        if direction == 'BULLISH':
            entry_price = fva['nested_fva_low']
            if entry_price is None: # Fallback
                # Need to find the overlapping FVG low
                # build_fva_from_it_points doesn't return the full FVG object, just the ID if available
                # Let's search fvgs for the overlapping one
                overlap_fvg = None
                for f in fvgs:
                    if f['fvg_high'] >= fva_low and f['fvg_low'] <= fva_low:
                        overlap_fvg = f
                        break
                entry_price = overlap_fvg['fvg_low'] if overlap_fvg else fva_low
            
            stop_loss = fva_low - buffer
            structural_target = recent_it_high['price_level']
        else:
            entry_price = fva['nested_fva_high']
            if entry_price is None: # Fallback
                overlap_fvg = None
                for f in fvgs:
                    if f['fvg_low'] <= fva_high and f['fvg_high'] >= fva_high:
                        overlap_fvg = f
                        break
                entry_price = overlap_fvg['fvg_high'] if overlap_fvg else fva_high
                
            stop_loss = fva_high + buffer
            structural_target = recent_it_low['price_level']
            
        risk = abs(entry_price - stop_loss)
        if risk <= 0:
            continue
            
        tp_2r = entry_price + (risk * 2.0) if direction == 'BULLISH' else entry_price - (risk * 2.0)
        tp_4r = entry_price + (risk * 4.0) if direction == 'BULLISH' else entry_price - (risk * 4.0)
        
        tp_2r_dist = abs(tp_2r - entry_price)
        tp_4r_dist = abs(tp_4r - entry_price)
        struct_dist = abs(structural_target - entry_price)
        
        # use_target = min(structural_target_distance, tp_4r_distance)
        if struct_dist < tp_4r_dist:
            use_target = structural_target
        else:
            use_target = tp_4r
            
        # But minimum must reach tp_2r, else SKIP
        if abs(use_target - entry_price) < tp_2r_dist:
            continue
            
        # Overlapping FVG type
        overlap_fvg_type = 'PFVG' # Default
        for f in fvgs:
            if (direction == 'BULLISH' and f['fvg_high'] >= fva_low and f['fvg_low'] <= fva_low) or \
               (direction == 'BEARISH' and f['fvg_low'] <= fva_high and f['fvg_high'] >= fva_high):
                overlap_fvg_type = f['fvg_type']
                overlap_fvg_high = f['fvg_high']
                overlap_fvg_low = f['fvg_low']
                break
        else:
            overlap_fvg_high = fva_high
            overlap_fvg_low = fva_low

        signals.append({
            'strategy': 'FVA_IDEAL',
            'instrument': instrument,
            'timeframe': timeframe,
            'signal_datetime': curr_dt,
            'direction': direction,
            'entry_price': round(entry_price, 5),
            'stop_loss': round(stop_loss, 5),
            'tp_2r': round(tp_2r, 5),
            'tp_4r': round(use_target, 5), # We use the optimized target as tp_4r field
            'risk_pips': round(risk * pip_multiplier, 2),
            'fva_high': round(fva_high, 5),
            'fva_low': round(fva_low, 5),
            'nested_fva_high': round(fva['nested_fva_high'], 5) if fva['nested_fva_high'] else None,
            'nested_fva_low': round(fva['nested_fva_low'], 5) if fva['nested_fva_low'] else None,
            'overlapping_fvg_high': round(overlap_fvg_high, 5),
            'overlapping_fvg_low': round(overlap_fvg_low, 5),
            'overlapping_fvg_type': overlap_fvg_type,
            'structural_target': round(structural_target, 5),
            'structural_target_type': 'IT_HIGH' if direction == 'BULLISH' else 'IT_LOW',
            'probability_arrays': 3,
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

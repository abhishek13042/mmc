import os
import sys
import pandas as pd
import numpy as np

# Setup paths for imports
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
MMC_DIR = os.path.join(ROOT_DIR, 'mmc_backtest')
if ROOT_DIR not in sys.path: sys.path.insert(0, ROOT_DIR)
if MMC_DIR not in sys.path: sys.path.insert(0, MMC_DIR)

# Import from modules
from modules.data_engine import fetch_candles
from modules.video2_market_structure import scan_it_points, build_fva_from_it_points
from modules.video1_pd_arrays import scan_candles_for_fvgs, get_pip_multiplier
from modules.video5_candle_science import get_candle_science_bias
from modules.video3_4_order_flow import scan_candles_for_ofls

def scan_fva_good(df, instrument, timeframe):
    """
    SUPER-OPTIMIZED Strategy 3 Scanner (O(N)).
    Uses sequential pointers to avoid quadratic re-scanning.
    """
    signals = []
    pip_multiplier = get_pip_multiplier(instrument)
    
    # Pre-calculate indicators
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    all_fvgs = sorted(scan_candles_for_fvgs(df, instrument), key=lambda x: x['candle3_datetime'])
    all_it_points = sorted(scan_it_points(df), key=lambda x: x['datetime'])
    
    # Group indicators for easy pointer access
    it_highs = [p for p in all_it_points if p['point_type'] == 'IT_HIGH']
    it_lows = [p for p in all_it_points if p['point_type'] == 'IT_LOW']
    
    # Pointers
    high_ptr = 0
    low_ptr = 0
    fvg_ptr = 0
    
    recent_it_high = None
    recent_it_low = None
    visible_fvgs = []

    for i in range(100, len(df)):
        current_candle = df.iloc[i]
        curr_dt = current_candle['datetime']
        current_price = current_candle['close']
        ema = df['ema_50'].iloc[i]
        
        # 1. Update Indicators using Pointers
        while high_ptr < len(it_highs) and it_highs[high_ptr]['datetime'] <= curr_dt:
            recent_it_high = it_highs[high_ptr]
            high_ptr += 1
            
        while low_ptr < len(it_lows) and it_lows[low_ptr]['datetime'] <= curr_dt:
            recent_it_low = it_lows[low_ptr]
            low_ptr += 1
            
        while fvg_ptr < len(all_fvgs) and all_fvgs[fvg_ptr]['candle3_datetime'] <= curr_dt:
            visible_fvgs.append(all_fvgs[fvg_ptr])
            fvg_ptr += 1
            
        if not recent_it_high or not recent_it_low:
            continue
            
        # 2. Build FVA and Check conditions
        # (Using pre-calculated visible_fvgs and it_points up to curr_dt)
        fva = build_fva_from_it_points(
            recent_it_high['price_level'], 
            recent_it_low['price_level'], 
            instrument, 
            visible_fvgs, 
            [] # it_points not strictly needed inside build_fva for 'good' check
        )
        
        if not fva or not fva['has_overlapping_fvg'] or fva['has_nested_fva'] or fva['is_sweep']:
            continue
            
        trend = "BULLISH" if current_price > ema else "BEARISH"
        fva_low = fva['fva_low']
        fva_high = fva['fva_high']
        
        # 3. Overlap Logic - Optimized search depth
        overlap_fvg = None
        # Only check the last 20 visible FVGs to avoid O(N^2)
        search_list = visible_fvgs[-20:]
        for f in reversed(search_list): 
            if (trend == 'BULLISH' and f['fvg_high'] >= fva_low and f['fvg_low'] <= fva_low) or \
               (trend == 'BEARISH' and f['fvg_low'] <= fva_high and f['fvg_high'] >= fva_high):
                if f['fvg_type'] in ['PFVG', 'BFVG']:
                    overlap_fvg = f
                    break
        
        if not overlap_fvg:
            continue
            
        # 4. Entry & Stop Loss
        fvg_low, fvg_high = overlap_fvg['fvg_low'], overlap_fvg['fvg_high']
        if trend == "BULLISH":
            oz_low, oz_high = max(fvg_low, fva_low), min(fvg_high, fva_low + (10 / pip_multiplier))
            entry = oz_low
        else:
            oz_high, oz_low = min(fvg_high, fva_high), max(fvg_low, fva_high - (10 / pip_multiplier))
            entry = oz_high
            
        if not (oz_low <= current_price <= oz_high):
            continue
            
        # Final Signal Construction
        signals.append({
            'strategy': 'FVA_GOOD',
            'instrument': instrument,
            'timeframe': timeframe,
            'signal_datetime': curr_dt,
            'direction': trend,
            'entry_price': entry,
            'stop_loss': recent_it_low['price_level'] if trend == 'BULLISH' else recent_it_high['price_level'],
            'tp_2r': entry + (abs(entry - (recent_it_low['price_level'] if trend == 'BULLISH' else recent_it_high['price_level'])) * 2) if trend == 'BULLISH' else entry - (abs(entry - (recent_it_low['price_level'] if trend == 'BULLISH' else recent_it_high['price_level'])) * 2),
            'tp_4r': recent_it_high['price_level'] if trend == 'BULLISH' else recent_it_low['price_level'],
            'risk_pips': round(abs(entry - (recent_it_low['price_level'] if trend == 'BULLISH' else recent_it_high['price_level'])) * pip_multiplier, 2)
        })
        
    return signals

if __name__ == "__main__":
    try:
        df = fetch_candles('EURUSD', '1H')
        if df is not None and not df.empty:
            test_df = df.tail(1000).copy()
            signals = scan_fva_good(test_df, 'EURUSD', '1H')
            print(f"Scanner OK | FVA Good Signals: {len(signals)}")
        else:
            print("No data found for EURUSD 1H")
    except Exception as e:
        print(f"Error in scanner: {e}")

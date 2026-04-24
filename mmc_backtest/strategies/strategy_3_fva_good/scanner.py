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
    Scans for 'Good' FVA setups based on:
    - Overlapping FVG (PFVG or BFVG)
    - No Nested FVA
    - No Liquidity Sweep
    - Candle Science Bias Alignment (HIGH/MEDIUM confidence)
    """
    signals = []
    pip_multiplier = get_pip_multiplier(instrument)
    
    # Calculate EMA 50
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    # Buffers for SL
    if 'JPY' in instrument:
        buffer = 0.02
    elif 'XAU' in instrument:
        buffer = 0.20
    else:
        buffer = 0.0002

    # Start scanning
    for i in range(100, len(df)):
        current_candle = df.iloc[i]
        current_price = current_candle['close']
        current_time = current_candle['datetime']
        ema = df['ema_50'].iloc[i]
        
        # Determine trend based on EMA
        trend = "BULLISH" if current_price > ema else "BEARISH"
        
        # Sub-dataframe up to current candle
        window = df.iloc[:i+1]
        
        # 1. Get IT Points
        it_points = scan_it_points(window)
        it_highs = [p for p in it_points if p['point_type'] == 'IT_HIGH']
        it_lows = [p for p in it_points if p['point_type'] == 'IT_LOW']
        
        if not it_highs or not it_lows:
            continue
            
        recent_it_high = it_highs[-1]
        recent_it_low = it_lows[-1]
        
        # SAFETY CHECK: IT High must be above IT Low
        if recent_it_high['price_level'] <= recent_it_low['price_level']:
            continue
        
        # 2. Get FVGs
        fvgs = scan_candles_for_fvgs(window, instrument)
        
        # 3. Build FVA
        fva = build_fva_from_it_points(
            recent_it_high['price_level'], 
            recent_it_low['price_level'], 
            instrument, 
            fvgs, 
            it_points
        )
        
        if not fva:
            continue
            
        # 4. Check "Good" FVA Conditions
        if not fva['has_overlapping_fvg'] or fva['has_nested_fva'] or fva['is_sweep']:
            continue
            
        fva_low = fva['fva_low']
        fva_high = fva['fva_high']
        
        # Only PFVG or BFVG
        overlap_fvg = None
        for f in fvgs:
            if (trend == 'BULLISH' and f['fvg_high'] >= fva_low and f['fvg_low'] <= fva_low) or \
               (trend == 'BEARISH' and f['fvg_low'] <= fva_high and f['fvg_high'] >= fva_high):
                overlap_fvg = f
                break
        
        if not overlap_fvg or overlap_fvg['fvg_type'] not in ['PFVG', 'BFVG']:
            continue
            
        # 5. Check Candle Science Bias (HARD requirement)
        cs_bias = get_candle_science_bias(instrument, current_time)
        if cs_bias['overall_bias'] != trend:
            continue
        if cs_bias['bias_confidence'] not in ['HIGH', 'MEDIUM']:
            continue

        # 6. Price at Overlap Zone
        fvg_low = overlap_fvg['fvg_low']
        fvg_high = overlap_fvg['fvg_high']
        
        if trend == "BULLISH":
            oz_low = max(fvg_low, fva_low)
            oz_high = min(fvg_high, fva_low + (10 / pip_multiplier))
            in_zone = oz_low <= current_price <= oz_high
            entry = oz_low
        else: # BEARISH
            oz_high = min(fvg_high, fva_high)
            oz_low = max(fvg_low, fva_high - (10 / pip_multiplier))
            in_zone = oz_low <= current_price <= oz_high
            entry = oz_high
            
        if not in_zone:
            continue
            
        # 7. Stop Loss from OFL swing point
        ofls = scan_candles_for_ofls(window, instrument)
        if not ofls:
            continue
        
        matching_ofls = [o for o in ofls if o['direction'] == trend]
        if not matching_ofls:
            continue
            
        latest_ofl = matching_ofls[-1]
        sl = latest_ofl['swing_point_price']
        sl = sl - buffer if trend == "BULLISH" else sl + buffer
        
        # Risk and TP
        risk = abs(entry - sl)
        if risk <= 0: continue
        
        tp_2r = entry + (risk * 2) if trend == "BULLISH" else entry - (risk * 2)
        tp_4r = entry + (risk * 4) if trend == "BULLISH" else entry - (risk * 4)
        
        # Structural Target
        structural_target = recent_it_high['price_level'] if trend == "BULLISH" else recent_it_low['price_level']
        
        if trend == "BULLISH":
            use_target = min(structural_target, tp_4r)
            if use_target < tp_2r: continue
        else:
            use_target = max(structural_target, tp_4r)
            if use_target > tp_2r: continue
            
        signals.append({
            'strategy': 'FVA_GOOD',
            'instrument': instrument,
            'timeframe': timeframe,
            'signal_datetime': current_time,
            'direction': trend,
            'entry_price': entry,
            'stop_loss': sl,
            'tp_2r': tp_2r,
            'tp_4r': use_target,
            'risk_pips': round(risk * pip_multiplier, 2),
            'fva_high': fva_high,
            'fva_low': fva_low,
            'probability_arrays': 2,
            'overlapping_fvg_type': overlap_fvg['fvg_type'],
            'overlap_zone_high': oz_high,
            'overlap_zone_low': oz_low,
            'candle_science_bias': cs_bias['overall_bias'],
            'candle_science_confidence': cs_bias['bias_confidence'],
            'ofl_swing_price': latest_ofl['swing_point_price'],
            'conditions_met': ['GOOD_FVA', 'CS_ALIGNMENT', 'OFL_SWING_SL'],
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

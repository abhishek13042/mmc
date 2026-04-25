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
from modules.video1_pd_arrays import scan_candles_for_fvgs, get_pip_multiplier
from modules.video2_market_structure import scan_it_points
from modules.video3_4_order_flow import scan_candles_for_ofls
from modules.video5_candle_science import get_candle_science_bias

def analyze_candle_visual(candle):
    """
    Arjo's Visual Candle Definitions (Video 5)
    30% and 35% thresholds represent 'small' and 'large' wicks.
    """
    open_p, high_p, low_p, close_p = candle['open'], candle['high'], candle['low'], candle['close']
    total_range = high_p - low_p
    if total_range == 0: return {'type': 'NEUTRAL', 'next': 'NEUTRAL'}
    
    upper_wick = high_p - max(open_p, close_p)
    lower_wick = min(open_p, close_p) - low_p
    upper_wick_ratio = upper_wick / total_range
    lower_wick_ratio = lower_wick / total_range
    direction = 'UP' if close_p > open_p else 'DOWN'
    
    # DISRESPECT (Small wick at top/bottom)
    if direction == 'UP' and upper_wick_ratio < lower_wick_ratio and upper_wick_ratio < 0.30:
        return {'type': 'DISRESPECT_BULLISH', 'next': 'CONTINUE_HIGHER'}
    if direction == 'DOWN' and lower_wick_ratio < upper_wick_ratio and lower_wick_ratio < 0.30:
        return {'type': 'DISRESPECT_BEARISH', 'next': 'CONTINUE_LOWER'}
        
    # RESPECT (Long wick at top/bottom)
    if lower_wick_ratio >= 0.35:
        return {'type': 'RESPECT_BULLISH', 'next': 'CONTINUE_HIGHER'}
    if upper_wick_ratio >= 0.35:
        return {'type': 'RESPECT_BEARISH', 'next': 'CONTINUE_LOWER'}
        
    return {'type': 'NEUTRAL', 'next': 'NEUTRAL'}

def scan_candle_science(df_htf, df_ltf, instrument, htf, ltf):
    """
    SUPER-OPTIMIZED Strategy 5 Scanner (O(N)).
    """
    signals = []
    pip_multiplier = get_pip_multiplier(instrument)
    
    # 1. Pre-calculate all indicators
    all_ofls = sorted(scan_candles_for_ofls(df_ltf, instrument), key=lambda x: x['datetime'])
    all_it_points = sorted(scan_it_points(df_ltf), key=lambda x: x['datetime'])
    
    # 2. Map OFLs for easy directional lookup
    # Grouping by datetime is not needed if we use pointers, but since we need MOST RECENT matching direction:
    ofl_ptr = 0
    it_ptr = 0
    current_ofl_bull = None
    current_ofl_bear = None
    recent_it_high = None
    recent_it_low = None

    for i in range(50, len(df_htf)):
        htf_candle = df_htf.iloc[i-1]
        htf_dt = htf_candle['datetime']
        ltf_limit_dt = df_htf.iloc[i]['datetime']
        
        # 1. Update Indicators using Pointers to the LTF timeframe
        while ofl_ptr < len(all_ofls) and all_ofls[ofl_ptr]['datetime'] <= ltf_limit_dt:
            ofl = all_ofls[ofl_ptr]
            if ofl['direction'] == 'BULLISH': current_ofl_bull = ofl
            else: current_ofl_bear = ofl
            ofl_ptr += 1
            
        while it_ptr < len(all_it_points) and all_it_points[it_ptr]['datetime'] <= ltf_limit_dt:
            pt = all_it_points[it_ptr]
            if pt['point_type'] == 'IT_HIGH': recent_it_high = pt
            else: recent_it_low = pt
            it_ptr += 1
            
        # 2. HTF Candle Science Analysis
        analysis = analyze_candle_visual(htf_candle)
        if analysis['type'] == 'NEUTRAL':
            continue
            
        direction = 'BULLISH' if analysis['next'] == 'CONTINUE_HIGHER' else 'BEARISH'
        
        # 3. 3-TF Bias Alignment (Pre-calculated in modules)
        bias = get_candle_science_bias(instrument, htf_dt)
        if bias['overall_bias'] != direction or bias['bias_confidence'] not in ['HIGH', 'MEDIUM']:
            continue
            
        # 4. LTF Confluence
        target_ofl = current_ofl_bull if direction == 'BULLISH' else current_ofl_bear
        if not target_ofl or target_ofl['probability_label'] not in ['HIGH', 'MEDIUM'] or target_ofl.get('fvg_type') != 'PFVG':
            continue
            
        # Entry, SL, TP
        entry_price = target_ofl['fvg_low'] if direction == 'BULLISH' else target_ofl['fvg_high']
        sl = target_ofl['swing_point_price']
        risk = abs(entry_price - sl)
        if risk <= 0: continue
        
        tp_2r = entry_price + (risk * 2.0) if direction == 'BULLISH' else entry_price - (risk * 2.0)
        tp_4r = entry_price + (risk * 4.0) if direction == 'BULLISH' else entry_price - (risk * 4.0)
        
        # Structural Target
        target_price = None
        if direction == 'BULLISH' and recent_it_high:
            target_price = recent_it_high['price_level']
        elif direction == 'BEARISH' and recent_it_low:
            target_price = recent_it_low['price_level']
        
        final_tp = target_price if target_price else tp_4r
        # Bound TP by 2R minimum and 4R maximum
        if direction == 'BULLISH':
            final_tp = max(tp_2r, min(final_tp, tp_4r))
        else:
            final_tp = min(tp_2r, max(final_tp, tp_4r))
            
        signals.append({
            'strategy': 'CANDLE_SCIENCE',
            'instrument': instrument,
            'htf': htf,
            'ltf': ltf,
            'signal_datetime': ltf_limit_dt,
            'direction': direction,
            'entry_price': round(entry_price, 5),
            'stop_loss': round(sl, 5),
            'tp_2r': round(tp_2r, 5),
            'tp_4r': round(final_tp, 5),
            'risk_pips': round(risk * pip_multiplier, 2)
        })
        
    return signals
        
    return signals

if __name__ == '__main__':
    try:
        df_d = fetch_candles('EURUSD', 'DAILY')
        df_h = fetch_candles('EURUSD', '1H')
        if df_d is not None and df_h is not None:
            signals = scan_candle_science(df_d.tail(100), df_h, 'EURUSD', 'DAILY', '1H')
            print(f"Scanner OK | Candle Science Signals: {len(signals)}")
            if signals:
                print(f"First Signal: {signals[0]['signal_datetime']} | Direction: {signals[0]['direction']}")
        else:
            print("Data not found.")
    except Exception as e:
        print(f"Error in scanner: {e}")

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
    Scans for Strategy 5: Candle Science Bias Entry.
    Requires aligned HTF and LTF dataframes.
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

    # Iterate through HTF candles
    # We need enough HTF data for bias check and signal analysis
    for i in range(50, len(df_htf)):
        # The signal is based on the LAST CLOSED HTF candle
        # Current candle i is the one where we are "standing"
        htf_candle = df_htf.iloc[i-1]
        htf_datetime = htf_candle['datetime']
        
        # 1. Condition 1: HTF Candle Science Signal (Visual)
        analysis = analyze_candle_visual(htf_candle)
        if analysis['type'] == 'NEUTRAL':
            continue
            
        direction = 'BULLISH' if analysis['next'] == 'CONTINUE_HIGHER' else 'BEARISH'
        
        # 2. Condition 2: 3-TF Bias Aligns
        # Note: we use the datetime of the HTF candle for the bias check context
        bias = get_candle_science_bias(instrument, htf_datetime)
        if bias['overall_bias'] != direction or bias['bias_confidence'] not in ['HIGH', 'MEDIUM']:
            continue
            
        # 3. Align with LTF
        # Find the LTF window up to the current HTF candle start time
        ltf_limit_dt = df_htf.iloc[i]['datetime']
        ltf_window = df_ltf[df_ltf['datetime'] <= ltf_limit_dt]
        
        if len(ltf_window) < 50:
            continue
            
        # 4. Condition 3 & 4: LTF OFL and PFVG
        ofls = scan_candles_for_ofls(ltf_window, instrument)
        if not ofls:
            continue
            
        # Find most recent OFL in matching direction with PFVG
        matching_ofl = None
        for ofl in reversed(ofls):
            if ofl['direction'] == direction and ofl['probability_label'] in ['HIGH', 'MEDIUM']:
                # Check for associated PFVG
                # In our system, ofl usually has an associated FVG
                if ofl.get('fvg_type') == 'PFVG':
                    matching_ofl = ofl
                    break
        
        if not matching_ofl:
            continue
            
        # Entry, SL, TP
        entry_price = matching_ofl['fvg_low'] if direction == 'BULLISH' else matching_ofl['fvg_high']
        sl = matching_ofl['swing_point_price']
        
        risk = abs(entry_price - sl)
        if risk <= 0: continue
        
        tp_2r = entry_price + (risk * 2.0) if direction == 'BULLISH' else entry_price - (risk * 2.0)
        tp_4r = entry_price + (risk * 4.0) if direction == 'BULLISH' else entry_price - (risk * 4.0)
        
        # Structural target on entry TF: nearest IT_HIGH (bull) / IT_LOW (bear)
        from modules.video2_market_structure import scan_it_points
        it_points = scan_it_points(ltf_window)
        target_price = None
        
        if direction == 'BULLISH':
            highs = [p['price_level'] for p in it_points if p['point_type'] == 'IT_HIGH' and p['price_level'] > entry_price]
            if highs: target_price = min(highs)
        else:
            lows = [p['price_level'] for p in it_points if p['point_type'] == 'IT_LOW' and p['price_level'] < entry_price]
            if lows: target_price = max(lows)
            
        if not target_price:
            target_price = tp_4r
            
        # Final TP logic: closer of structural or 4R, but must be at least 2R
        if direction == 'BULLISH':
            final_tp = min(target_price, tp_4r)
            if final_tp < tp_2r: continue
        else:
            final_tp = max(target_price, tp_4r)
            if final_tp > tp_2r: continue
            
        signals.append({
            'strategy': 'CANDLE_SCIENCE',
            'instrument': instrument,
            'htf': htf,
            'ltf': ltf,
            'signal_datetime': ltf_window.iloc[-1]['datetime'],
            'direction': direction,
            'htf_candle_type': analysis['type'],
            'htf_confidence': 100, # Visual confirmation is binary in this logic
            'bias_confidence': bias['bias_confidence'],
            'ltf_ofl_probability': matching_ofl['probability_label'],
            'entry_price': round(entry_price, 5),
            'stop_loss': round(sl, 5),
            'tp_2r': round(tp_2r, 5),
            'tp_4r': round(final_tp, 5),
            'risk_pips': round(risk * pip_multiplier, 2),
            'conditions_met': ['HTF_CS_SIGNAL', '3TF_BIAS_ALIGN', 'LTF_OFL_PFVG'],
        })
        
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

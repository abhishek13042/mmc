import pandas as pd
import numpy as np
from modules.video1_pd_arrays import scan_candles_for_fvgs, scan_candles_for_swings, get_pip_multiplier
from modules.video10_context import build_context_area
from modules.video11_entries import validate_entry_timeframe
from modules.video3_4_order_flow import scan_candles_for_ofls, full_order_flow_scan
from modules.data_engine import fetch_candles

def scan_sharp_turn(df_context_tf, df_entry_tf, instrument, context_tf, entry_tf) -> list[dict]:
    """
    MMC Strategy 6: Sharp Turn Entry Scanner (Optimized)
    """
    signals = []
    
    # Validation
    val = validate_entry_timeframe(context_tf, entry_tf, 'sharp_turn')
    if not val['is_valid']:
        print(f"Timeframe validation failed: {val['reason']}")
        return []

    pip_mult = get_pip_multiplier(instrument)
    
    # PRE-SCAN everything once to avoid O(N^2)
    print(f"Pre-scanning {len(df_context_tf)} context candles and {len(df_entry_tf)} entry candles...")
    htf_fvgs = scan_candles_for_fvgs(df_context_tf, instrument)
    htf_swings = scan_candles_for_swings(df_context_tf)
    htf_ofls = scan_candles_for_ofls(df_context_tf, instrument)
    
    ltf_fvgs = scan_candles_for_fvgs(df_entry_tf, instrument)
    ltf_ofls = scan_candles_for_ofls(df_entry_tf, instrument)
    
    # Helper to get contexts at a specific HTF candle index i
    def get_contexts_at_i(i):
        current_time = df_context_tf.iloc[i]['datetime']
        # Filter pre-scanned items up to this time
        swings_to_date = [s for s in htf_swings if s['datetime'] <= current_time]
        fvgs_to_date = [f for f in htf_fvgs if f['candle3_datetime'] <= current_time]
        ofls_to_date = [o for o in htf_ofls if o['datetime'] <= current_time]
        
        contexts = []
        for ofl in ofls_to_date:
            if ofl['probability_label'] in ['HIGH', 'MEDIUM']:
                boundary = {
                    'price': ofl['fvg_low'] if ofl['direction'] == 'BULLISH' else ofl['fvg_high'],
                    'low': ofl['fvg_low'],
                    'high': ofl['fvg_high'],
                    'boundary_type': 'FVG'
                }
                # build_context_area needs the lists
                ctx = build_context_area(instrument, context_tf, boundary, ofl['direction'], swings_to_date, fvgs_to_date)
                if ctx:
                    contexts.append(ctx)
        return contexts

    print("Scanning for signals...")
    # Alignment logic: iterate through context TF
    for i in range(50, len(df_context_tf)):
        ctx_candle = df_context_tf.iloc[i]
        ctx_time = ctx_candle['datetime']
        
        active_contexts = get_contexts_at_i(i)
        
        # Window in LTF corresponding to this HTF candle
        start_time = df_context_tf.iloc[i-1]['datetime'] if i > 0 else df_entry_tf.iloc[0]['datetime']
        entry_window = df_entry_tf[(df_entry_tf['datetime'] > start_time) & (df_entry_tf['datetime'] <= ctx_time)]
        
        for ctx in active_contexts:
            if not ctx['is_active'] or ctx['is_target_reached']:
                continue
                
            direction = ctx['direction']
            fvg_in_low = ctx['boundary_low']
            fvg_in_high = ctx['boundary_high']
            
            for j_idx, entry_candle in entry_window.iterrows():
                j = df_entry_tf.index.get_loc(j_idx)
                
                entered = False
                if direction == 'BULLISH':
                    if entry_candle['low'] <= fvg_in_high and entry_candle['low'] >= fvg_in_low:
                        entered = True
                else: # BEARISH
                    if entry_candle['high'] >= fvg_in_low and entry_candle['high'] <= fvg_in_high:
                        entered = True
                
                if entered:
                    # Look for FVG_OUT (removed hard 3-candle limit)
                    for k in range(1, 21):
                        if j + k + 1 >= len(df_entry_tf): break
                        
                        target_time = df_entry_tf.iloc[j+k+1]['datetime']
                        
                        # Find FVG_OUT in pre-scanned list
                        fvg_out = None
                        for f in ltf_fvgs:
                            if f['candle3_datetime'] == target_time and f['direction'] == direction:
                                fvg_out = f
                                break
                        
                        if not fvg_out: continue
                        
                        # Speed quality scoring
                        candles_to_form = k
                        if candles_to_form <= 2:
                            speed_quality = 'FAST'
                            speed_score = 3
                        elif candles_to_form <= 5:
                            speed_quality = 'MEDIUM'
                            speed_score = 2
                        elif candles_to_form <= 10:
                            speed_quality = 'SLOW'
                            speed_score = 1
                        else:
                            speed_quality = 'VERY_SLOW'
                            speed_score = 0

                        # OFL Check
                        recent_ofl = None
                        for o in ltf_ofls:
                            if o['datetime'] <= target_time:
                                recent_ofl = o
                                break # ltf_ofls is sorted reverse datetime
                                
                        if not recent_ofl or recent_ofl['probability_label'] not in ['HIGH', 'MEDIUM']:
                            continue
                            
                        # ENTRY PRICE and SL (No buffer)
                        entry_price = fvg_out['fvg_low'] if direction == 'BULLISH' else fvg_out['fvg_high']
                        stop_loss = recent_ofl['swing_point_price']
                        risk = abs(entry_price - stop_loss)
                        
                        if risk <= 0: continue
                        
                        tp_2r = entry_price + (risk * 2) if direction == 'BULLISH' else entry_price - (risk * 2)
                        context_target = ctx['target_price']
                        
                        if abs(entry_price - context_target) < (risk * 2):
                            continue
                            
                        signals.append({
                            'strategy': 'SHARP_TURN',
                            'instrument': instrument,
                            'context_tf': context_tf,
                            'entry_tf': entry_tf,
                            'signal_datetime': str(target_time),
                            'direction': direction,
                            'entry_price': float(entry_price),
                            'stop_loss': float(stop_loss),
                            'tp_2r': float(tp_2r),
                            'tp_4r': float(entry_price + (risk * 4) if direction == 'BULLISH' else entry_price - (risk * 4)),
                            'risk_pips': float(risk * pip_mult),
                            'fvg_in_high': float(fvg_in_high),
                            'fvg_in_low': float(fvg_in_low),
                            'fvg_out_high': float(fvg_out['fvg_high']),
                            'fvg_out_low': float(fvg_out['fvg_low']),
                            'fvg_out_type': fvg_out['fvg_type'],
                            'candles_to_form_fvg_out': candles_to_form,
                            'speed_quality': speed_quality,
                            'speed_score': speed_score,
                            'context_target': float(context_target),
                            'context_target_type': ctx['target_type'],
                            'ofl_swing': float(recent_ofl['swing_point_price']),
                            'ofl_probability': recent_ofl['probability_label'],
                            'conditions_met': ['ACTIVE_CONTEXT', 'FVG_IN_ENTERED', 'FVG_OUT_FORMED', 'OFL_CONFIRMED', 'TF_VALIDATED'],
                        })
                        break
    
    seen = set()
    unique_signals = []
    for s in signals:
        key = (s['signal_datetime'], s['direction'])
        if key not in seen:
            unique_signals.append(s)
            seen.add(key)
            
    print(f"Scan complete. Found {len(unique_signals)} signals.")
    return unique_signals

if __name__ == '__main__':
    from modules.data_engine import fetch_candles
    print("Testing Strategy 6 Scanner (Optimized)...")
    try:
        df_d = fetch_candles('EURUSD', 'DAILY')
        df_h = fetch_candles('EURUSD', '1H')
        signals = scan_sharp_turn(df_d, df_h, 'EURUSD', 'DAILY', '1H')
        print(f"Scanner OK | Sharp Turn Signals: {len(signals)}")
    except Exception as e:
        print(f"Error during scan: {e}")

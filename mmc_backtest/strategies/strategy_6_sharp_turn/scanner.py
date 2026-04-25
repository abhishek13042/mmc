import pandas as pd
import numpy as np
from modules.video1_pd_arrays import scan_candles_for_fvgs, scan_candles_for_swings, get_pip_multiplier
from modules.video10_context import build_context_area
from modules.video11_entries import validate_entry_timeframe
from modules.video3_4_order_flow import scan_candles_for_ofls, full_order_flow_scan
from modules.data_engine import fetch_candles

def scan_sharp_turn(df_context_tf, df_entry_tf, instrument, context_tf, entry_tf) -> list[dict]:
    """
    SUPER-OPTIMIZED Strategy 6 Scanner (O(N)).
    """
    signals = []
    pip_mult = get_pip_multiplier(instrument)
    
    # 1. Pre-calculate all indicators
    htf_fvgs = sorted(scan_candles_for_fvgs(df_context_tf, instrument), key=lambda x: x['candle3_datetime'])
    htf_swings = sorted(scan_candles_for_swings(df_context_tf), key=lambda x: x['datetime'])
    htf_ofls = sorted(scan_candles_for_ofls(df_context_tf, instrument), key=lambda x: x['datetime'])
    
    ltf_fvgs = sorted(scan_candles_for_fvgs(df_entry_tf, instrument), key=lambda x: x['candle3_datetime'])
    ltf_ofls = sorted(scan_candles_for_ofls(df_entry_tf, instrument), key=lambda x: x['datetime'])
    
    # 2. Pointers for HTF indicators
    h_fvg_ptr, h_swing_ptr, h_ofl_ptr = 0, 0, 0
    l_fvg_ptr, l_ofl_ptr = 0, 0
    
    visible_h_fvgs, visible_h_swings = [], []
    current_h_ofl = None
    
    # Map LTF FVGs for fast lookup
    ltf_fvg_lookup = {f['candle3_datetime']: f for f in ltf_fvgs}
    
    # 3. Optimization: Iterate HTF to build active contexts
    for i in range(50, len(df_context_tf)):
        ctx_candle = df_context_tf.iloc[i]
        curr_dt = ctx_candle['datetime']
        
        # Update HTF Pointers
        while h_fvg_ptr < len(htf_fvgs) and htf_fvgs[h_fvg_ptr]['candle3_datetime'] <= curr_dt:
            visible_h_fvgs.append(htf_fvgs[h_fvg_ptr]); h_fvg_ptr += 1
        while h_swing_ptr < len(htf_swings) and htf_swings[h_swing_ptr]['datetime'] <= curr_dt:
            visible_h_swings.append(htf_swings[h_swing_ptr]); h_swing_ptr += 1
        while h_ofl_ptr < len(htf_ofls) and htf_ofls[h_ofl_ptr]['datetime'] <= curr_dt:
            current_h_ofl = htf_ofls[h_ofl_ptr]; h_ofl_ptr += 1
            
        if not current_h_ofl or current_h_ofl['probability_label'] not in ['HIGH', 'MEDIUM']:
            continue
            
        # Build Context Area (This is still somewhat expensive but only once per HTF candle)
        boundary = {
            'price': current_h_ofl['fvg_low'] if current_h_ofl['direction'] == 'BULLISH' else current_h_ofl['fvg_high'],
            'low': current_h_ofl['fvg_low'], 'high': current_h_ofl['fvg_high']
        }
        ctx = build_context_area(instrument, context_tf, boundary, current_h_ofl['direction'], visible_h_swings, visible_h_fvgs)
        if not ctx or not ctx['is_active']: continue
        
        # Align with LTF window
        start_time = df_context_tf.iloc[i-1]['datetime']
        entry_window = df_entry_tf[(df_entry_tf['datetime'] > start_time) & (df_entry_tf['datetime'] <= curr_dt)]
        
        for j_idx, ltf_candle in entry_window.iterrows():
            ltf_dt = ltf_candle['datetime']
            direction = ctx['direction']
            
            entered = (direction == 'BULLISH' and ltf_candle['low'] <= ctx['boundary_high'] and ltf_candle['low'] >= ctx['boundary_low']) or \
                      (direction == 'BEARISH' and ltf_candle['high'] >= ctx['boundary_low'] and ltf_candle['high'] <= ctx['boundary_high'])
            
            if entered:
                # Look for FVG_OUT in next 20 LTF candles
                j_pos = df_entry_tf.index.get_loc(j_idx)
                for k in range(1, 21):
                    if j_pos + k + 1 >= len(df_entry_tf): break
                    out_dt = df_entry_tf.iloc[j_pos+k+1]['datetime']
                    fvg_out = ltf_fvg_lookup.get(out_dt)
                    
                    if fvg_out and fvg_out['direction'] == direction:
                        # Confirm LTF OFL
                        target_ofl = None
                        # Use a pointer or fast search for ltf ofl at out_dt
                        for o in reversed(ltf_ofls):
                            if o['datetime'] <= out_dt:
                                target_ofl = o; break
                        
                        if not target_ofl or target_ofl['probability_label'] not in ['HIGH', 'MEDIUM']: continue
                        
                        entry_price = fvg_out['fvg_low'] if direction == 'BULLISH' else fvg_out['fvg_high']
                        sl = target_ofl['swing_point_price']
                        risk = abs(entry_price - sl)
                        if risk <= 0 or abs(entry_price - ctx['target_price']) < (risk * 2): continue
                        
                        signals.append({
                            'strategy': 'SHARP_TURN',
                            'instrument': instrument,
                            'signal_datetime': str(out_dt),
                            'direction': direction,
                            'entry_price': round(entry_price, 5),
                            'stop_loss': round(sl, 5),
                            'tp_2r': round(entry_price + (risk * 2) if direction == 'BULLISH' else entry_price - (risk * 2), 5),
                            'tp_4r': round(entry_price + (risk * 4) if direction == 'BULLISH' else entry_price - (risk * 4), 5),
                            'context_target': round(ctx['target_price'], 5),
                            'risk_pips': round(risk * pip_mult, 2)
                        })
                        break
                        
    return signals
    
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

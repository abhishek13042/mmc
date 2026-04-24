import pandas as pd
import numpy as np
from modules.video1_pd_arrays import scan_candles_for_fvgs, scan_candles_for_swings, get_pip_multiplier
from modules.video10_context import build_context_area
from modules.video11_entries import validate_entry_timeframe, run_mmc_checklist
from modules.video3_4_order_flow import scan_candles_for_ofls
from modules.data_engine import fetch_candles

def scan_order_flow_entry(df_context_tf, df_entry_tf, instrument, context_tf, entry_tf) -> list[dict]:
    """
    MMC Strategy 7: Order Flow Entry (Two OFLs)
    """
    signals = []
    
    # 1. TF Validation
    val = validate_entry_timeframe(context_tf, entry_tf, 'order_flow')
    if not val['is_valid']:
        return []

    pip_mult = get_pip_multiplier(instrument)
    
    # Pre-scan HTF
    print(f"Pre-scanning {len(df_context_tf)} context candles...")
    htf_fvgs = scan_candles_for_fvgs(df_context_tf, instrument)
    htf_swings = scan_candles_for_swings(df_context_tf)
    htf_ofls = scan_candles_for_ofls(df_context_tf, instrument)
    
    # Pre-scan LTF
    print(f"Pre-scanning {len(df_entry_tf)} entry candles...")
    ltf_ofls = scan_candles_for_ofls(df_entry_tf, instrument)
    
    # Alignment and Scan
    for i in range(50, len(df_context_tf)):
        ctx_candle = df_context_tf.iloc[i]
        ctx_time = ctx_candle['datetime']
        
        # Get active context areas at this HTF candle
        swings_to_date = [s for s in htf_swings if s['datetime'] <= ctx_time]
        fvgs_to_date = [f for f in htf_fvgs if f['candle3_datetime'] <= ctx_time]
        ofls_to_date = [o for o in htf_ofls if o['datetime'] <= ctx_time]
        
        active_contexts = []
        for ofl in ofls_to_date:
            if ofl['probability_label'] in ['HIGH', 'MEDIUM']:
                boundary = {
                    'price': ofl['fvg_low'] if ofl['direction'] == 'BULLISH' else ofl['fvg_high'],
                    'low': ofl['fvg_low'],
                    'high': ofl['fvg_high'],
                    'boundary_type': 'FVG'
                }
                ctx = build_context_area(instrument, context_tf, boundary, ofl['direction'], swings_to_date, fvgs_to_date)
                if ctx: active_contexts.append(ctx)

        # LTF window
        start_time = df_context_tf.iloc[i-1]['datetime'] if i > 0 else df_entry_tf.iloc[0]['datetime']
        entry_window = df_entry_tf[(df_entry_tf['datetime'] > start_time) & (df_entry_tf['datetime'] <= ctx_time)]
        
        for ctx in active_contexts:
            if not ctx['is_active'] or ctx['is_target_reached']:
                continue
                
            direction = ctx['direction']
            
            for j_idx, entry_candle in entry_window.iterrows():
                j_time = entry_candle['datetime']
                
                # CONDITION 2: TWO OFLs In Same Direction
                # Get all OFLs on entry TF up to this candle
                ofls_entry = [o for o in ltf_ofls if o['datetime'] <= j_time and o['direction'] == direction]
                
                if len(ofls_entry) < 2:
                    continue
                
                # ofls_entry should be sorted by datetime desc already
                ofl_2 = ofls_entry[0] # most recent
                ofl_1 = ofls_entry[1] # older
                
                if ofl_1['probability_label'] not in ['HIGH', 'MEDIUM'] or ofl_2['probability_label'] not in ['HIGH', 'MEDIUM']:
                    continue
                    
                if not ofl_1['is_confirmed'] or not ofl_2['is_confirmed']:
                    continue

                # CONDITION 3: OFL 2 Must Be Inside Context Area
                # We use the context boundary as the filter
                if direction == 'BULLISH':
                    # Must be above context boundary low
                    if ofl_2['fvg_low'] < ctx['context_low']: continue
                    # And below or within the target? Actually usually we just check if it's within the "area"
                    if ofl_2['fvg_high'] > ctx['context_high']: continue
                else: # BEARISH
                    if ofl_2['fvg_high'] > ctx['context_high']: continue
                    if ofl_2['fvg_low'] < ctx['context_low']: continue

                # CONDITION 5: MMC 10-Point Checklist
                # Mock news for now as we don't have a news feed passed in
                checklist = run_mmc_checklist(
                    instrument, context_tf, entry_tf, direction, 'ORDER_FLOW',
                    j_time, [], ctx, fvg_quality=ofl_2['fvg_type'], fva_quality=ofl_2.get('fva_type', 'GOOD')
                )
                
                items = checklist['checklist_items']
                hard_items = [1, 2, 3, 4, 7, 8, 9]
                warn_items = [5, 6, 10]
                
                failed_hard = [it['name'] for it in items if it['num'] in hard_items and it['status'] == 'FAIL']
                # Special rule: Item 4 (FVA Quality) fail if WEAK
                if ofl_2.get('fva_type') == 'WEAK':
                    failed_hard.append('FVA QUALITY')
                
                if failed_hard:
                    continue
                    
                warns = [it['name'] for it in items if it['num'] in warn_items and it['status'] in ['FAIL', 'WARN']]
                
                # Signal Found
                entry_price = ofl_2['fvg_low'] if direction == 'BULLISH' else ofl_2['fvg_high']
                stop_loss = ofl_2['swing_point_price']
                risk = abs(entry_price - stop_loss)
                if risk <= 0: continue
                
                tp_2r = entry_price + (risk * 2) if direction == 'BULLISH' else entry_price - (risk * 2)
                context_target = ctx['target_price']
                
                # Skip if target closer than 2R
                if abs(entry_price - context_target) < (risk * 2):
                    continue
                    
                # Use context_target if >= 2R, else use 4R (as fallback for stats)
                final_tp = context_target if abs(entry_price - context_target) >= (risk * 2) else (entry_price + (risk * 4) if direction == 'BULLISH' else entry_price - (risk * 4))

                signals.append({
                    'strategy': 'ORDER_FLOW_ENTRY',
                    'instrument': instrument,
                    'context_tf': context_tf,
                    'entry_tf': entry_tf,
                    'signal_datetime': str(j_time),
                    'direction': direction,
                    'entry_price': float(entry_price),
                    'stop_loss': float(stop_loss),
                    'tp_2r': float(tp_2r),
                    'tp_4r': float(entry_price + (risk * 4) if direction == 'BULLISH' else entry_price - (risk * 4)),
                    'risk_pips': float(risk * pip_mult),
                    'ofl_1_swing': float(ofl_1['swing_point_price']),
                    'ofl_1_probability': ofl_1['probability_label'],
                    'ofl_1_fvg_type': ofl_1['fvg_type'],
                    'ofl_2_swing': float(ofl_2['swing_point_price']),
                    'ofl_2_probability': ofl_2['probability_label'],
                    'ofl_2_fvg_type': ofl_2['fvg_type'],
                    'context_target': float(context_target),
                    'context_target_type': ctx['target_type'],
                    'checklist_passed': len(failed_hard) == 0,
                    'checklist_failed_items': failed_hard,
                    'checklist_warn_items': warns,
                    'conditions_met': ['CONTEXT_ACTIVE', 'TWO_OFLS_FOUND', 'OFL2_INSIDE_CONTEXT', 'TF_VALIDATED', 'CHECKLIST_HARD_PASS'],
                })
                break
                
    # Deduplicate
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
    print("Testing Strategy 7 Scanner...")
    df_d = fetch_candles('EURUSD', 'DAILY')
    df_15 = fetch_candles('EURUSD', '15M')
    if df_d is not None and df_15 is not None:
        signals = scan_order_flow_entry(df_d, df_15, 'EURUSD', 'DAILY', '15M')
        print(f"Scanner OK | Order Flow Signals: {len(signals)}")

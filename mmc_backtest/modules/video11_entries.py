import pandas as pd
import numpy as np
from modules.video1_pd_arrays import get_pip_multiplier
from modules.video3_4_order_flow import full_order_flow_scan
from modules.video9_time import does_time_support_id, is_in_killzone

# --- CONSTANTS ---
CONTEXT_TF_ENTRY_MAP = {
    'MONTHLY': {'sharp_turn': 'DAILY', 'order_flow': '4H'},
    'WEEKLY':  {'sharp_turn': '4H',    'order_flow': '1H'},
    'DAILY':   {'sharp_turn': '1H',    'order_flow': '15M'},
    '4H':      {'sharp_turn': '15M',   'order_flow': '5M'},
    '1H':      {'sharp_turn': '5M',    'order_flow': '1M'},
    '15M':     {'sharp_turn': '1M',    'order_flow': '1M'}
}

TIMEFRAME_WEIGHTS = {
    'MONTHLY': 7, 'WEEKLY': 6, 'DAILY': 5,
    '4H': 4, '1H': 3, '15M': 2, '5M': 1, '1M': 1
}

def validate_entry_timeframe(context_tf, entry_tf, entry_type):
    """Enforce minimum entry TF rules from Video 11."""
    min_tf = CONTEXT_TF_ENTRY_MAP.get(context_tf, {}).get(entry_type.lower())
    if not min_tf:
        return {'is_valid': True, 'reason': "No specific mapping, allowing by default."}
        
    min_weight = TIMEFRAME_WEIGHTS[min_tf]
    entry_weight = TIMEFRAME_WEIGHTS.get(entry_tf, 0)
    
    is_valid = entry_weight >= min_weight
    
    reason = f"Valid timeframe."
    if not is_valid:
        reason = f"Minimum entry TF for {context_tf} {entry_type} is {min_tf}. Selected {entry_tf}."
    elif entry_weight > min_weight:
        reason = f"Above minimum — extra confirmation via higher TF ({entry_tf})."
        
    return {
        'is_valid': is_valid,
        'minimum_tf': min_tf,
        'reason': reason
    }

def calculate_risk_reward(entry_price, stop_loss, direction, instrument):
    """Standalone RR calculator."""
    pip_mult = get_pip_multiplier(instrument)
    risk = abs(entry_price - stop_loss)
    risk_pips = risk * pip_mult
    
    if risk_pips <= 1e-9:
        raise ValueError("Invalid SL: produces zero or negative risk")
        
    if direction.upper() in ['BULLISH', 'LONG']:
        tp_1r = entry_price + risk
        tp_2r = entry_price + (risk * 2)
    else:
        tp_1r = entry_price - risk
        tp_2r = entry_price - (risk * 2)
        
    return {
        'risk_pips': round(float(risk_pips), 2),
        'tp_1r': round(float(tp_1r), 5),
        'tp_2r': round(float(tp_2r), 5),
        'reward_pips_1r': round(float(risk_pips), 2),
        'reward_pips_2r': round(float(risk_pips * 2), 2)
    }

def build_sharp_turn(context_area, entry_tf, fvg_in, fvg_out, direction, instrument):
    """Build a Sharp Turn entry."""
    # Find most recent OFL for stop loss placement (Hard Institutional Rule)
    ofl_results = full_order_flow_scan(instrument, entry_tf)
    ofls = ofl_results.get('all_ofls', [])
    recent_ofl = ofls[0] if ofls else None
        
    if direction.upper() == 'BEARISH':
        entry_price = fvg_out['fvg_high']
        # Rule: stop_loss = most recent OFL High Price
        if recent_ofl and recent_ofl['direction'] == 'BEARISH':
            stop_loss = recent_ofl['swing_point_price']
        else:
            stop_loss = fvg_in['fvg_high'] # Fallback
    else:
        entry_price = fvg_out['fvg_low']
        # Rule: stop_loss = most recent OFL Low Price
        if recent_ofl and recent_ofl['direction'] == 'BULLISH':
            stop_loss = recent_ofl['swing_point_price']
        else:
            stop_loss = fvg_in['fvg_low'] # Fallback
            
    rr = calculate_risk_reward(entry_price, stop_loss, direction, instrument)
    
    return {
        'entry_type': 'SHARP_TURN',
        'direction': direction,
        'entry_price': entry_price,
        'stop_loss': stop_loss,
        'risk_pips': rr['risk_pips'],
        'tp_1r': rr['tp_1r'],
        'tp_2r': rr['tp_2r'],
        'speed_quality': 'FAST', # Mock for now
        'context_id': context_area.get('id') if context_area else None
    }

def run_mmc_checklist(instrument, context_tf, entry_tf, direction, entry_type, 
                      current_datetime, news_events, context_area, fvg_quality='PFVG', fva_quality='IDEAL'):
    """Run the full 10-item MMC pre-trade checklist."""
    items = []
    
    # 1. Direction (Aligned with Context TF OFL)
    ofl_scan = full_order_flow_scan(instrument, context_tf)
    recent_ofl = ofl_scan.get('most_recent_ofl')
    dir_status = 'PASS' if recent_ofl and recent_ofl['direction'] == direction else 'FAIL'
    items.append({'num': 1, 'name': 'DIRECTION', 'status': dir_status, 'detail': 'Aligned with higher TF OFL'})
    
    # 2. Narrative
    narrative_status = 'PASS' if context_area and context_area.get('is_active') else 'FAIL'
    items.append({'num': 2, 'name': 'NARRATIVE', 'status': narrative_status, 'detail': 'Context area active'})
    
    # 3. FVG Quality
    fvg_status = 'PASS' if fvg_quality in ['PFVG', 'BFVG'] else 'FAIL'
    items.append({'num': 3, 'name': 'FVG QUALITY', 'status': fvg_status, 'detail': fvg_quality})
    
    # 4. FVA Quality
    fva_status = 'PASS' if fva_quality in ['IDEAL', 'GOOD'] else 'WARN'
    items.append({'num': 4, 'name': 'FVA QUALITY', 'status': fva_status, 'detail': fva_quality})
    
    # 5. Higher TF Time (News)
    time_support = does_time_support_id(instrument, current_datetime, news_events)
    news_status = 'PASS' if time_support['time_supports'] else 'FAIL'
    items.append({'num': 5, 'name': 'H-TF TIME', 'status': news_status, 'detail': time_support['reason']})
    
    # 6. Lower TF Time (Killzone)
    kz = is_in_killzone(current_datetime, instrument)
    kz_status = 'PASS' if kz['in_killzone'] else 'WARN'
    items.append({'num': 6, 'name': 'L-TF TIME', 'status': kz_status, 'detail': f"In Killzone: {kz['in_killzone']}"})
    
    # 7. Context Target
    context_status = 'PASS' if context_area and not context_area.get('is_target_reached') else 'FAIL'
    items.append({'num': 7, 'name': 'CONTEXT', 'status': context_status, 'detail': 'Target not reached'})
    
    # 8. Entry TF Rule
    tf_val = validate_entry_timeframe(context_tf, entry_tf, entry_type)
    tf_status = 'PASS' if tf_val['is_valid'] else 'FAIL'
    items.append({'num': 8, 'name': 'ENTRY TF', 'status': tf_status, 'detail': tf_val['reason']})
    
    # 9. Confirmation Sequence
    items.append({'num': 9, 'name': 'CONFIRMATION', 'status': 'PASS', 'detail': f"{entry_type} formed"})
    
    # 10. Big Three News
    big_three_fail = False
    for event in news_events:
        if event.get('is_big_three'):
            event_time = pd.to_datetime(event['event_datetime'])
            curr_time = pd.to_datetime(current_datetime)
            if abs((event_time - curr_time).total_seconds()) <= 1800: # 30 min window
                big_three_fail = True
                break
    b3_status = 'FAIL' if big_three_fail else 'PASS'
    items.append({'num': 10, 'name': 'BIG THREE', 'status': b3_status, 'detail': 'No Major Event +/- 30m'})
    
    failed = [i for i in items if i['status'] == 'FAIL']
    return {
        'passed': len(failed) == 0,
        'checklist_items': items,
        'failed_count': len(failed)
    }

def build_order_flow_entry(context_area, entry_tf, ofl_1, ofl_2, direction, instrument):
    """Build an Order Flow entry using exactly two OFLs."""
    if not ofl_1 or not ofl_2:
        raise ValueError("Order flow entry requires exactly two OFLs")
        
    if ofl_1['direction'] != ofl_2['direction']:
        raise ValueError("Both OFLs must be the same direction")
        
    if direction.upper() == 'BEARISH':
        entry_price = ofl_2['fvg_high']
        stop_loss = ofl_2['swing_point_price'] # SL above most recent OFL
    else:
        entry_price = ofl_2['fvg_low']
        stop_loss = ofl_2['swing_point_price'] # SL below most recent OFL
        
    rr = calculate_risk_reward(entry_price, stop_loss, direction, instrument)
    
    return {
        'entry_type': 'ORDER_FLOW',
        'direction': direction,
        'entry_price': entry_price,
        'stop_loss': stop_loss,
        'risk_pips': rr['risk_pips'],
        'tp_1r': rr['tp_1r'],
        'tp_2r': rr['tp_2r'],
        'context_id': context_area.get('id') if context_area else None
    }

import pandas as pd
import numpy as np
from modules.video1_pd_arrays import get_pip_multiplier
from modules.video2_market_structure import fair_value_theory_check
from modules.video3_4_order_flow import full_order_flow_scan
from modules.data_engine import fetch_candles

def find_first_opposing_pda(boundary_price, direction, swing_list, fvg_list, instrument):
    """Find the FIRST opposing PDArray — this is always the context target."""
    candidates = []
    
    if direction == 'BULLISH':
        # Look for first premium above
        for s in swing_list:
            if s['swing_level'] > boundary_price: # Simplified swing check
                candidates.append({'type': 'SWING_HIGH', 'price': s['swing_level']})
        for f in fvg_list:
            if f['direction'] == 'BEARISH' and f['fvg_low'] > boundary_price:
                candidates.append({'type': 'BEARISH_FVG', 'price': f['fvg_low']})
        
        if not candidates:
            return {'pda_type': 'PCH', 'pda_price': boundary_price * 1.01, 'distance_pips': 100}
            
        candidates.sort(key=lambda x: x['price']) # Nearest above
        
    else: # BEARISH
        # Look for first discount below
        for s in swing_list:
            if s['swing_level'] < boundary_price:
                candidates.append({'type': 'SWING_LOW', 'price': s['swing_level']})
        for f in fvg_list:
            if f['direction'] == 'BULLISH' and f['fvg_high'] < boundary_price:
                candidates.append({'type': 'BULLISH_FVG', 'price': f['fvg_high']})
                
        if not candidates:
            return {'pda_type': 'PCL', 'pda_price': boundary_price * 0.99, 'distance_pips': 100}
            
        candidates.sort(key=lambda x: x['price'], reverse=True) # Nearest below

    pda = candidates[0]
    pip_mult = get_pip_multiplier(instrument)
    dist = abs(pda['price'] - boundary_price) * pip_mult
    
    return {
        'pda_type': pda['type'],
        'pda_price': pda['price'],
        'distance_pips': round(float(dist), 2)
    }

def build_context_area(instrument, timeframe, boundary_dict, direction, swing_list, fvg_list):
    """Build a complete context area from boundary to first opposing PDA."""
    target = find_first_opposing_pda(boundary_dict['price'], direction, swing_list, fvg_list, instrument)
    if not target:
        return None
        
    target_price = target['pda_price']
    
    if direction == 'BULLISH':
        ctx_low = boundary_dict['low']
        ctx_high = target_price
    else:
        ctx_high = boundary_dict['high']
        ctx_low = target_price
        
    pip_mult = get_pip_multiplier(instrument)
    size = abs(ctx_high - ctx_low) * pip_mult
    
    if size <= 0:
        return None

    # Defense mapping
    bt = boundary_dict.get('boundary_type', 'SWING_POINT')
    defense = 'FLOD'
    if bt == 'FVA': defense = 'ODD'
    elif bt in ['SWING_POINT', 'PCH', 'PCL', 'FVG']: defense = 'LOD'
    
    return {
        'id': f"ctx_{pd.Timestamp.now().strftime('%Y%m%d%H%M%S')}",
        'instrument': instrument,
        'timeframe': timeframe,
        'context_type': 'USUAL',
        'direction': direction,
        'boundary_type': bt,
        'boundary_high': boundary_dict['high'],
        'boundary_low': boundary_dict['low'],
        'target_type': target['pda_type'],
        'target_price': target_price,
        'context_high': ctx_high,
        'context_low': ctx_low,
        'context_size_pips': round(float(size), 2),
        'defense_type': defense,
        'is_active': True,
        'is_target_reached': False,
        'is_unusual': False
    }

def detect_unusual_context(fva_high, fva_low, direction, recent_candles_df, fvg_list, instrument):
    """Detect if usual context has failed = unusual context triggered."""
    price = recent_candles_df.iloc[-1]['close']
    
    # Check Fair Value Theory
    state = fair_value_theory_check(price, fva_high, fva_low, direction)
    if state['market_state'] == 'SEEKING_LIQUIDITY':
        return {
            'is_unusual': True,
            'trigger': 'FVA_DISRESPECTED',
            'explanation': "FVA disrespected — market seeking liquidity not offering fair value",
            'new_target': fva_low * 0.99 if direction == 'BULLISH' else fva_high * 1.01
        }
            
    return {'is_unusual': False, 'trigger': None, 'explanation': "Usual context intact", 'new_target': None}

def full_context_scan(instrument, timeframe):
    """Scan all active context areas on a given TF."""
    from modules.video1_pd_arrays import scan_candles_for_fvgs, scan_candles_for_swings
    
    df = fetch_candles(instrument, timeframe)
    fvgs = scan_candles_for_fvgs(df, instrument)
    swings = scan_candles_for_swings(df)
    ofl_results = full_order_flow_scan(instrument, timeframe)
    
    contexts = []
    # Using active OFLs as boundaries
    for ofl in ofl_results.get('active_ofls', []):
        boundary = {
            'price': ofl['fvg_low'] if ofl['direction'] == 'BULLISH' else ofl['fvg_high'],
            'low': ofl['fvg_low'],
            'high': ofl['fvg_high'],
            'boundary_type': 'FVG'
        }
        ctx = build_context_area(instrument, timeframe, boundary, ofl['direction'], swings, fvgs)
        if ctx:
            contexts.append(ctx)
            
    return contexts

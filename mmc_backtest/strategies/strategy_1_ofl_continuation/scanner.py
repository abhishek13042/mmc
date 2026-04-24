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
from mmc_backtest.modules.video2_market_structure import scan_it_points
from mmc_backtest.modules.video3_4_order_flow import scan_candles_for_ofls
from mmc_backtest.backtest.data_loader import fetch_candles

def load_strategy_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return {}

def scan_ofl_continuation(df, instrument, timeframe):
    """
    SUPER-OPTIMIZED Strategy 1 Scanner.
    $O(N)$ linear complexity using sequential pointers.
    """
    config = load_strategy_config()
    params = config.get('parameters', {})
    
    signals = []
    pip_multiplier = get_pip_multiplier(instrument)
    buffer_pips = params.get('buffer_pips', 2)
    buffer_price = buffer_pips / pip_multiplier

    print(f"Pre-calculating Indicators for {timeframe}...")
    all_fvgs = scan_candles_for_fvgs(df, instrument)
    # Ensure ascending order for pointers
    all_ofls = sorted(scan_candles_for_ofls(df, instrument), key=lambda x: x['datetime'])
    all_it_points = sorted(scan_it_points(df), key=lambda x: x['datetime'])
    
    fvg_by_dt = defaultdict(list)
    for f in all_fvgs:
        fvg_by_dt[f['candle3_datetime']].append(f)
        
    it_highs = [p for p in all_it_points if p['point_type'] == 'IT_HIGH']
    it_lows = [p for p in all_it_points if p['point_type'] == 'IT_LOW']
    
    # Pointers
    ofl_ptr = 0
    high_ptr = 0
    low_ptr = 0
    
    active_pfvgs = [] 
    current_ofl = None
    recent_it_high = None
    recent_it_low = None
    
    print(f"Scanning {len(df)} candles...")
    for i in range(50, len(df)):
        current_candle = df.iloc[i]
        curr_dt = current_candle['datetime']
        curr_close = current_candle['close']
        
        # 1. Update Indicators using Pointers
        while ofl_ptr < len(all_ofls) and all_ofls[ofl_ptr]['datetime'] <= curr_dt:
            current_ofl = all_ofls[ofl_ptr]
            ofl_ptr += 1
            
        while high_ptr < len(it_highs) and it_highs[high_ptr]['datetime'] <= curr_dt:
            recent_it_high = it_highs[high_ptr]
            high_ptr += 1
            
        while low_ptr < len(it_lows) and it_lows[low_ptr]['datetime'] <= curr_dt:
            recent_it_low = it_lows[low_ptr]
            low_ptr += 1
            
        # New FVGs for this candle
        new_fvgs = fvg_by_dt[curr_dt]
        allowed_fvgs_types = params.get('fvg_types_allowed', ['PFVG'])
        for nf in new_fvgs:
            if nf['fvg_type'] in allowed_fvgs_types:
                active_pfvgs.append({'data': nf, 'mitigated': False, 'created_at': curr_dt})
        
        if not current_ofl or not recent_it_high or not recent_it_low: 
            continue
        
        # 2. Range & Context Check
        equilibrium = (recent_it_high['price_level'] + recent_it_low['price_level']) / 2
        
        # 3. Strategy Rules
        # We only check the most recent non-mitigated candidates
        candidates = [f for f in active_pfvgs if not f['mitigated']]
        if not candidates: continue
            
        allowed_probs = params.get('ofl_probability_labels', ['HIGH', 'MEDIUM', 'LOW'])
        if current_ofl['probability_label'] not in allowed_probs or not current_ofl['is_confirmed']:
            continue
            
        ofl_dir = current_ofl['direction']
        matching_fvgs = [f['data'] for f in candidates if f['data']['direction'] == ofl_dir]
        if not matching_fvgs: continue
            
        target_fvg = matching_fvgs[-1]
        
        # Filter A: Discount / Premium
        if ofl_dir == 'BULLISH':
            if curr_close >= equilibrium: continue 
            entry_price = target_fvg['fvg_low']
            stop_loss = current_ofl['swing_point_price'] - buffer_price
            erl_target = recent_it_high['price_level'] 
        else:
            if curr_close <= equilibrium: continue 
            entry_price = target_fvg['fvg_high']
            stop_loss = current_ofl['swing_point_price'] + buffer_price
            erl_target = recent_it_low['price_level']

        # Filter B: Room to Move (Min RR to ERL)
        risk = abs(entry_price - stop_loss)
        if risk <= 0: continue
        
        risk_pips = risk * pip_multiplier
        if risk_pips < params.get('min_risk_pips', 3.0):
            continue
            
        reward_to_erl = abs(erl_target - entry_price)
        rr_to_erl = reward_to_erl / risk
        if rr_to_erl < params.get('min_rr', 2.0):
            continue

        # 4. Entry Detection
        can_enter = current_candle['low'] <= entry_price <= current_candle['high']
            
        if not can_enter:
            # Mitigation logic - also O(K) where K is active FVG count
            for pfvg in active_pfvgs:
                if not pfvg['mitigated']:
                    if current_candle['low'] <= pfvg['data']['fvg_low'] <= current_candle['high'] or \
                       current_candle['low'] <= pfvg['data']['fvg_high'] <= current_candle['high']:
                        pfvg['mitigated'] = True
            continue

        # 5. Signal Found
        final_rr_to_erl = min(rr_to_erl, params.get('max_rr_cap', 25.0))
        
        signals.append({
            'strategy': 'OFL_CONTINUATION',
            'instrument': instrument,
            'timeframe': timeframe,
            'signal_datetime': curr_dt,
            'direction': ofl_dir,
            'entry_price': round(entry_price, 5),
            'stop_loss': round(stop_loss, 5),
            'tp_2r': round(entry_price + (risk * 2.0) if ofl_dir == 'BULLISH' else entry_price - (risk * 2.0), 5),
            'tp_erl': round(entry_price + (risk * final_rr_to_erl) if ofl_dir == 'BULLISH' else entry_price - (risk * final_rr_to_erl), 5),
            'risk_pips': round(risk_pips, 2),
            'range_high': recent_it_high['price_level'],
            'range_low': recent_it_low['price_level'],
            'ofl_probability': current_ofl['probability_label']
        })
        
        # Mark as mitigated
        for pfvg in active_pfvgs:
            if pfvg['data'] == target_fvg:
                pfvg['mitigated'] = True
        
    return signals

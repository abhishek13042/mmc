import sys, os
import pandas as pd
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../../..')))

from mmc_backtest.modules.video1_pd_arrays import (
    scan_candles_for_fvgs, get_pip_multiplier
)
from mmc_backtest.modules.video3_4_order_flow import (
    scan_candles_for_ofls
)
from mmc_backtest.backtest.data_loader import fetch_candles

def scan_pch_pcl_sweep(df, instrument, timeframe) -> list[dict]:
    """
    SUPER-OPTIMIZED Strategy 9 Scanner (O(N)).
    """
    results = []
    pip_mult = get_pip_multiplier(instrument)
    
    # 1. Pre-calculate all indicators
    all_fvgs = sorted(scan_candles_for_fvgs(df, instrument), key=lambda x: x['candle3_datetime'])
    all_ofls = sorted(scan_candles_for_ofls(df, instrument), key=lambda x: x['datetime'])
    
    # 2. Pointers
    fvg_ptr = 0
    ofl_ptr = 0
    visible_fvgs = []
    current_ofl_bull = None
    current_ofl_bear = None
    
    # 3. Minimum Wick
    min_wick = 0.20 if 'XAU' in instrument else 0.0002

    for i in range(50, len(df) - 2):
        current_candle = df.iloc[i]
        next_candle = df.iloc[i+1]
        curr_dt = current_candle['datetime']
        
        while fvg_ptr < len(all_fvgs) and all_fvgs[fvg_ptr]['candle3_datetime'] <= curr_dt:
            visible_fvgs.append(all_fvgs[fvg_ptr]); fvg_ptr += 1
            
        while ofl_ptr < len(all_ofls) and all_ofls[ofl_ptr]['datetime'] <= curr_dt:
            o = all_ofls[ofl_ptr]
            if o['direction'] == 'BULLISH': current_ofl_bull = o
            else: current_ofl_bear = o
            ofl_ptr += 1
            
        if not visible_fvgs: continue
        
        active_fvg = next((f for f in reversed(visible_fvgs) if f['fvg_type'] in ['PFVG', 'BFVG']), None)
        if not active_fvg: continue
        
        direction = active_fvg['direction']
        
        in_fvg = (direction == 'BULLISH' and current_candle['low'] <= active_fvg['fvg_high']) or \
                 (direction == 'BEARISH' and current_candle['high'] >= active_fvg['fvg_low'])
        if not in_fvg: continue
        
        sweep_confirmed = False
        if direction == 'BULLISH':
            if next_candle['low'] < current_candle['low'] and next_candle['close'] > current_candle['low']:
                if (current_candle['low'] - next_candle['low']) >= min_wick: sweep_confirmed = True
        else: 
            if next_candle['high'] > current_candle['high'] and next_candle['close'] < current_candle['high']:
                if (next_candle['high'] - current_candle['high']) >= min_wick: sweep_confirmed = True
                
        if not sweep_confirmed: continue
        
        target_ofl = current_ofl_bull if direction == 'BULLISH' else current_ofl_bear
        if not target_ofl or target_ofl['probability_label'] not in ['HIGH', 'MEDIUM']: continue
        
        entry_price = active_fvg['fvg_low'] if direction == 'BULLISH' else active_fvg['fvg_high']
        sl = target_ofl['swing_point_price']
        risk = abs(entry_price - sl)
        if risk > 0:
            results.append({
                'strategy': 'PCH_PCL_SWEEP', 'instrument': instrument, 'signal_datetime': str(curr_dt), 'direction': direction,
                'entry_price': round(entry_price, 5), 'stop_loss': round(sl, 5),
                'tp_2r': round(entry_price + (risk * 2) if direction == 'BULLISH' else entry_price - (risk * 2), 5),
                'tp_4r': round(entry_price + (risk * 4) if direction == 'BULLISH' else entry_price - (risk * 4), 5),
                'risk_pips': round(risk * pip_mult, 2)
            })
    return results

    return results

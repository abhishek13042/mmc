import sys, os
import pandas as pd
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../../..')))

from mmc_backtest.modules.video1_pd_arrays import (
    scan_candles_for_fvgs, scan_candles_for_swings,
    get_pip_multiplier, check_mitigation
)
from mmc_backtest.modules.video2_market_structure import (
    scan_it_points, calculate_fva_boundaries,
    fair_value_theory_check, determine_trend
)
from mmc_backtest.modules.video3_4_order_flow import (
    scan_candles_for_ofls
)
from mmc_backtest.backtest.data_loader import fetch_candles

def scan_it_retracement(df, instrument, timeframe) -> list[dict]:
    """
    SUPER-OPTIMIZED Strategy 8 Scanner (O(N)).
    """
    results = []
    pip_mult = get_pip_multiplier(instrument)
    
    # 1. Pre-calculate all indicators
    all_it_points = sorted(scan_it_points(df), key=lambda x: x['datetime'])
    all_ofls = sorted(scan_candles_for_ofls(df, instrument), key=lambda x: x['datetime'])
    
    # 2. Pointers
    it_ptr = 0
    ofl_ptr = 0
    visible_it_points = []
    current_ofl_bull = None
    current_ofl_bear = None
    
    # Track when IT points are broken
    broken_it_events = [] 

    for i in range(50, len(df)):
        current = df.iloc[i]
        curr_dt = current['datetime']
        
        while it_ptr < len(all_it_points) and all_it_points[it_ptr]['datetime'] <= curr_dt:
            visible_it_points.append(all_it_points[it_ptr]); it_ptr += 1
            
        while ofl_ptr < len(all_ofls) and all_ofls[ofl_ptr]['datetime'] <= curr_dt:
            o = all_ofls[ofl_ptr]
            if o['direction'] == 'BULLISH': current_ofl_bull = o
            else: current_ofl_bear = o
            ofl_ptr += 1
            
        if len(visible_it_points) < 2: continue
        
        # Detect Breakouts
        for it in visible_it_points[-5:]: # Check very recent IT points
            if it['point_type'] == 'IT_HIGH' and current['close'] > it['price_level']:
                prev_low = next((p for p in reversed(visible_it_points) if p['point_type'] == 'IT_LOW' and p['datetime'] < it['datetime']), None)
                if prev_low: broken_it_events.append({'it': it, 'companion': prev_low, 'break_idx': i, 'direction': 'BEARISH'})
            elif it['point_type'] == 'IT_LOW' and current['close'] < it['price_level']:
                prev_high = next((p for p in reversed(visible_it_points) if p['point_type'] == 'IT_HIGH' and p['datetime'] < it['datetime']), None)
                if prev_high: broken_it_events.append({'it': it, 'companion': prev_high, 'break_idx': i, 'direction': 'BULLISH'})

        # Filter events
        broken_it_events = [e for e in broken_it_events if i - e['break_idx'] <= 15 and not e.get('invalid')]
        
        for event in broken_it_events:
            direction = event['direction']
            fva = calculate_fva_boundaries(max(event['it']['price_level'], event['companion']['price_level']), min(event['it']['price_level'], event['companion']['price_level']))
            if not fva: continue
            
            if (direction == 'BULLISH' and current['close'] < fva['fva_low']) or (direction == 'BEARISH' and current['close'] > fva['fva_high']):
                event['invalid'] = True; continue
                
            if (current['low'] <= fva['fva_high'] and current['high'] >= fva['fva_low']):
                target_ofl = current_ofl_bull if direction == 'BULLISH' else current_ofl_bear
                if target_ofl and target_ofl['probability_label'] in ['HIGH', 'MEDIUM'] and (target_ofl['fvg_low'] >= fva['fva_low'] and target_ofl['fvg_high'] <= fva['fva_high']):
                    entry_price = target_ofl['fvg_low'] if direction == 'BULLISH' else target_ofl['fvg_high']
                    sl = target_ofl['swing_point_price']
                    risk = abs(entry_price - sl)
                    if risk > 0:
                        results.append({
                            'strategy': 'IT_RETRACEMENT', 'instrument': instrument, 'signal_datetime': str(curr_dt), 'direction': direction,
                            'entry_price': round(entry_price, 5), 'stop_loss': round(sl, 5),
                            'tp_2r': round(entry_price + (risk * 2) if direction == 'BULLISH' else entry_price - (risk * 2), 5),
                            'tp_4r': round(entry_price + (risk * 4) if direction == 'BULLISH' else entry_price - (risk * 4), 5),
                            'risk_pips': round(risk * pip_mult, 2)
                        })
                        broken_it_events.remove(event); break
    return results

    return results

if __name__ == "__main__":
    # Quick test
    try:
        df = fetch_candles('EURUSD', '1H')
        if df is not None:
            signals = scan_it_retracement(df.tail(1000), 'EURUSD', '1H')
            print(f"Found {len(signals)} signals.")
            if signals:
                print(signals[0])
    except Exception as e:
        print(f"Test error: {e}")

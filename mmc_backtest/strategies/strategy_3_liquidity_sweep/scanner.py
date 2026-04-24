import sys
import os
import pandas as pd
import json

# Add project root and mmc_backtest folder to path for imports to work
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
MMC_DIR = os.path.join(ROOT_DIR, 'mmc_backtest')
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, MMC_DIR)

import json
from mmc_backtest.modules.video1_pd_arrays import scan_candles_for_fvgs, get_pip_multiplier, scan_candles_for_swings
from mmc_backtest.modules.video8_sweeps import (
    classify_liquidity_event, find_target_after_sweep
)
from mmc_backtest.backtest.data_loader import fetch_candles

def load_strategy_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return {}

def scan_liquidity_sweep(df, instrument, timeframe):
    """
    Optimized Scanner for Strategy 3: Liquidity Sweep Reversal.
    """
    config = load_strategy_config()
    params = config.get('parameters', {})
    allowed_sweep_types = params.get('sweep_types_allowed', ['SWEEP'])
    min_wick_ratio = params.get('min_wick_ratio', 0.5)

    signals = []
    pip_multiplier = get_pip_multiplier(instrument)
    buffer_pips = 20 if instrument == 'XAUUSD' else 2
    buffer_price = buffer_pips / pip_multiplier

    print("Pre-calculating Swings and FVGs...")
    all_swings = scan_candles_for_swings(df)
    all_fvgs = scan_candles_for_fvgs(df, instrument)

    for i in range(50, len(df) - 5):
        c = df.iloc[i]
        direction = "BULLISH" # Default to buy after sweep low
        
        # 1. Find recent HTF/ITF swing points to sweep
        eligible_swings = [s for s in all_swings if s['datetime'] < c['datetime']]
        if not eligible_swings: continue
        
        # Look for most recent swing low that was breached
        s = eligible_swings[-1]
        swept_level = s['swing_level']
        
        is_sweep_event = False
        if s['swing_type'] == "SWING_LOW" and c['low'] < swept_level and c['close'] > swept_level:
            is_sweep_event = True
            direction = "BULLISH"
        elif s['swing_type'] == "SWING_HIGH" and c['high'] > swept_level and c['close'] < swept_level:
            is_sweep_event = True
            direction = "BEARISH"
            
        if is_sweep_event:
            # 2. Check for Sweep Event using classification
            next_df = df.iloc[i+1 : i+6]
            event = classify_liquidity_event(
                swept_level, s['swing_type'], 
                c['high'], c['low'], c['close'], 
                next_df, instrument
            )
            
            if event and event['event_type'] in allowed_sweep_types:
                if event['wick_ratio'] >= min_wick_ratio:
                    # Verified Sweep!
                    target = find_target_after_sweep(swept_level, direction, all_swings, all_fvgs, instrument)
                    if not target: continue
                    
                    target_price = target['target_price']
                    entry_price = c['close']
                    stop_loss = c['low'] - buffer_price if direction == 'BULLISH' else c['high'] + buffer_price
                    
                    risk = abs(entry_price - stop_loss)
                    if risk <= 0: continue
                    
                    signals.append({
                        'strategy': 'LIQUIDITY_SWEEP',
                        'instrument': instrument,
                        'signal_datetime': c['datetime'],
                        'direction': direction,
                        'entry_price': round(entry_price, 5),
                        'stop_loss': round(stop_loss, 5),
                        'tp_target': round(target_price, 5),
                        'tp_2r': round(entry_price + (risk * 2.0) if direction == 'BULLISH' else entry_price - (risk * 2.0), 5),
                        'risk_pips': round(risk * pip_multiplier, 2),
                        'sweep_level': swept_level,
                        'wick_ratio': event['wick_ratio']
                    })
                    
    return signals

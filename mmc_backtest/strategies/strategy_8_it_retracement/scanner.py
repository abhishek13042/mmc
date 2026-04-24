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
    Walk-forward scan for IT High/Low Retracement setups.
    Uses df.iloc[:i] at each step — NO lookahead bias.
    Minimum window: 50 candles.
    """
    results = []
    pip_mult = get_pip_multiplier(instrument)

    print(f"Scanning {len(df)} candles for Strategy 8: IT Retracement...")

    for i in range(50, len(df)):
        window = df.iloc[:i]
        current = df.iloc[i]
        # In case index is not datetime, use string representation
        current_dt = str(current['datetime']) if 'datetime' in current else str(df.index[i])

        try:
            # Step 1: Get IT points in window
            it_points = scan_it_points(window)
            if not it_points or len(it_points) < 2:
                continue

            # Step 2: Find most recently broken IT point (within 20 candles)
            broken_it = None
            broken_direction = None
            search_start = max(0, len(window) - 20)

            # Look back from the current end of window to see if any IT point was broken
            for j in range(len(window) - 1, search_start, -1):
                candle_j = window.iloc[j]
                for it in it_points:
                    # Check if IT point was established BEFORE candle j
                    if pd.to_datetime(it['datetime']) >= pd.to_datetime(candle_j['datetime']):
                        continue
                        
                    if it['point_type'] == 'IT_HIGH':
                        if candle_j['close'] > it['price_level']:
                            broken_it = it
                            broken_direction = 'BEARISH' # Market breaking IT High = starting a bearish retracement context? 
                            # Wait, Arjo's words: "BULLISH (IT_LOW was broken, continuing higher)"
                            # "BEARISH (IT_HIGH was broken, continuing lower)"
                            # Let's align with the prompt's Condition 2 logic.
                            break
                    elif it['point_type'] == 'IT_LOW':
                        if candle_j['close'] < it['price_level']:
                            broken_it = it
                            broken_direction = 'BULLISH' # Breaking IT Low = starting bullish context
                            break
                if broken_it:
                    break

            if not broken_it:
                continue

            # Step 3: Get the IT point before the broken one to form FVA
            # For BULLISH: need the IT_HIGH before the broken IT_LOW
            # For BEARISH: need the IT_LOW before the broken IT_HIGH
            companion_it = None
            for it in reversed(it_points):
                if pd.to_datetime(it['datetime']) >= pd.to_datetime(broken_it['datetime']):
                    continue
                
                if broken_direction == 'BULLISH':
                    if it['point_type'] == 'IT_HIGH' and it['price_level'] > broken_it['price_level']:
                        companion_it = it
                        break
                elif broken_direction == 'BEARISH':
                    if it['point_type'] == 'IT_LOW' and it['price_level'] < broken_it['price_level']:
                        companion_it = it
                        break

            if not companion_it:
                continue

            # Step 4: Calculate FVA
            if broken_direction == 'BULLISH':
                it_high_price = companion_it['price_level']
                it_low_price  = broken_it['price_level']
            else:
                it_high_price = broken_it['price_level']
                it_low_price  = companion_it['price_level']

            fva = calculate_fva_boundaries(it_high_price, it_low_price)
            if not fva or fva['fva_size'] <= 0:
                continue

            fva_high = fva['fva_high']
            fva_low  = fva['fva_low']

            # Step 5: Check if current price is retracing into FVA
            # Must be within 15 candles of the break
            # Find the index where the break happened
            break_idx = -1
            for j in range(len(window)-1, -1, -1):
                c = window.iloc[j]
                if (broken_direction == 'BULLISH' and c['close'] < broken_it['price_level']) or \
                   (broken_direction == 'BEARISH' and c['close'] > broken_it['price_level']):
                    break_idx = j
                    break
            
            if break_idx == -1: continue
            
            candles_since_break = i - break_idx
            if candles_since_break > 15:
                continue

            price_in_fva = False
            if broken_direction == 'BULLISH':
                price_in_fva = (current['low'] <= fva_high
                                and current['high'] >= fva_low)
            else:
                price_in_fva = (current['high'] >= fva_low
                                and current['low'] <= fva_high)

            if not price_in_fva:
                continue

            # Step 6: Check FVA not violated
            # Bullish: no close below fva_low. Bearish: no close above fva_high.
            recent = window.iloc[break_idx:]
            if broken_direction == 'BULLISH':
                if any(recent['close'] < fva_low):
                    continue  # FVA disrespected
            else:
                if any(recent['close'] > fva_high):
                    continue  # FVA disrespected

            # Step 7: Find OFL inside FVA
            ofls = scan_candles_for_ofls(window, instrument)
            ofl_in_fva = None
            for ofl in reversed(ofls): # Most recent first
                if ofl['direction'] != broken_direction:
                    continue
                if ofl['probability_label'] not in ['HIGH', 'MEDIUM']:
                    continue
                
                # Must be inside FVA zone
                if (ofl['fvg_low'] >= fva_low and ofl['fvg_high'] <= fva_high):
                    ofl_in_fva = ofl
                    break

            if not ofl_in_fva:
                continue

            # Step 8: Confirm trend direction
            trend_result = determine_trend(it_points)
            if trend_result['trend'] != broken_direction:
                continue

            # Step 9: Calculate entry, SL, TP
            if broken_direction == 'BULLISH':
                entry_price = ofl_in_fva['fvg_low']
                stop_loss   = ofl_in_fva['swing_point_price']
            else:
                entry_price = ofl_in_fva['fvg_high']
                stop_loss   = ofl_in_fva['swing_point_price']

            risk = abs(entry_price - stop_loss)
            if risk <= 0:
                continue

            risk_pips = risk * pip_mult

            if broken_direction == 'BULLISH':
                tp_1r = entry_price + risk
                tp_2r = entry_price + risk * 2
                tp_4r = entry_price + risk * 4
            else:
                tp_1r = entry_price - risk
                tp_2r = entry_price - risk * 2
                tp_4r = entry_price - risk * 4

            # Step 10: Find structural target
            remaining_it = [p for p in it_points
                            if p['price_level'] != broken_it['price_level']]
            structural_target = None
            structural_target_type = None
            if broken_direction == 'BULLISH':
                highs_above = [p for p in remaining_it
                               if p['point_type'] == 'IT_HIGH'
                               and p['price_level'] > entry_price]
                if highs_above:
                    structural_target = min(highs_above,
                        key=lambda x: x['price_level'])['price_level']
                    structural_target_type = 'IT_HIGH'
            else:
                lows_below = [p for p in remaining_it
                              if p['point_type'] == 'IT_LOW'
                              and p['price_level'] < entry_price]
                if lows_below:
                    structural_target = max(lows_below,
                        key=lambda x: x['price_level'])['price_level']
                    structural_target_type = 'IT_LOW'

            # Minimum TP check (must be >= tp_2r distance)
            final_tp = tp_4r # Default
            if structural_target:
                struct_dist = abs(structural_target - entry_price)
                tp_4r_dist = abs(tp_4r - entry_price)
                
                # Use closer of struct or 4R
                if struct_dist < tp_4r_dist:
                    final_tp = structural_target
                else:
                    final_tp = tp_4r
                
                # Check min 2R
                if abs(final_tp - entry_price) < abs(tp_2r - entry_price):
                    continue  # Not enough room

            results.append({
                'strategy':              'IT_RETRACEMENT',
                'instrument':            instrument,
                'timeframe':             timeframe,
                'signal_datetime':       current_dt,
                'direction':             broken_direction,
                'entry_price':           round(entry_price, 5),
                'stop_loss':             round(stop_loss, 5),
                'tp_1r':                 round(tp_1r, 5),
                'tp_2r':                 round(tp_2r, 5),
                'tp_4r':                 round(final_tp, 5),
                'risk_pips':             round(risk_pips, 2),
                'fva_high':              round(fva_high, 5),
                'fva_low':               round(fva_low, 5),
                'broken_it_level':       round(broken_it['price_level'], 5),
                'broken_it_type':        broken_it['point_type'],
                'candles_since_break':   candles_since_break,
                'ofl_probability':       ofl_in_fva['probability_label'],
                'ofl_fvg_type':          ofl_in_fva.get('fvg_type', 'UNKNOWN'),
                'structural_target':     round(structural_target, 5)
                                         if structural_target else None,
                'structural_target_type': structural_target_type,
                'trend_confirmed':       True,
                'conditions_met':        ['IT_BROKEN', 'FVA_ESTABLISHED', 'RETRACEMENT', 'OFL_IN_FVA', 'TREND_CONFIRMED']
            })

        except Exception as e:
            # print(f"Error at index {i}: {e}")
            continue

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

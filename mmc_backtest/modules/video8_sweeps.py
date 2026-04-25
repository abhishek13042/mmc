import pandas as pd
import numpy as np
from modules.video1_pd_arrays import (
    scan_candles_for_fvgs,
    scan_candles_for_swings,
    validate_bullish_fvg,
    validate_bearish_fvg,
    get_pip_multiplier,
    check_mitigation
)
from modules.video3_4_order_flow import (
    scan_candles_for_ofls,
    build_ofl,
    validate_ofl_structure
)
from modules.data_engine import fetch_candles

# --- CONSTANTS ---
COMFORTABLE_CANDLE_THRESHOLD = 2
AGGRESSIVE_BODY_THRESHOLD    = 0.70

SWEEP_WICK_MIN_PIPS = {
    'EURUSD': 2.0,
    'GBPUSD': 2.0,
    'XAUUSD': 20.0
}

SWEEP_PROBABILITY_BASE       = 70.0
AGGRESSIVE_PENALTY           = 30.0
ORDER_FLOW_SWEEP_BONUS       = 15.0
CS_SWEEP_BONUS               = 10.0

def classify_liquidity_event(swept_level, sweep_type, candle_high, candle_low, candle_close, next_candles_df, instrument):
    event = "UNKNOWN"
    comfortable_candles = 0
    is_aggressive = False
    reason = ""
    
    # Check aggression of the candle AFTER the sweep
    if len(next_candles_df) > 0:
        c_after = next_candles_df.iloc[0]
        body = abs(c_after['close'] - c_after['open'])
        range_ = c_after['high'] - c_after['low']
        if range_ > 0 and (body / range_) > AGGRESSIVE_BODY_THRESHOLD:
            is_aggressive = True
            
    is_bullish_sweep = candle_low < swept_level and candle_close > swept_level
    is_bearish_sweep = candle_high > swept_level and candle_close < swept_level
    
    if is_bullish_sweep: # Swept LOWS
        for _, row in next_candles_df.iterrows():
            if row['close'] < swept_level:
                comfortable_candles += 1
        if comfortable_candles > COMFORTABLE_CANDLE_THRESHOLD:
            event = "RUN"
            reason = f"Comfortable below: {comfortable_candles} candles closed below level"
        elif candle_close > swept_level:
            event = "SWEEP"
            reason = "Clean sweep: immediate reversal above swept level"
        else:
            event = "RUN"
            reason = "No reversal: closed below swept level"
            
    elif is_bearish_sweep: # Swept HIGHS
        for _, row in next_candles_df.iterrows():
            if row['close'] > swept_level:
                comfortable_candles += 1
        if comfortable_candles > COMFORTABLE_CANDLE_THRESHOLD:
            event = "RUN"
            reason = f"Comfortable above: {comfortable_candles} candles closed above level"
        elif candle_close < swept_level:
            event = "SWEEP"
            reason = "Clean sweep: immediate reversal below swept level"
        else:
            event = "RUN"
            reason = "No reversal: closed above swept level"
    else:
        # If it didn't even reverse on the first candle, it's a RUN or not a sweep
        event = "RUN"
        reason = "No immediate reversal on the sweep candle"
        
    return {
        "event": event,
        "comfortable_candles": comfortable_candles,
        "is_aggressive": is_aggressive,
        "reason": reason
    }

def detect_order_flow_sweep(*args, **kwargs):
    """
    Detects an Order Flow Sweep (MSS) event.
    
    Supports two signatures:
    1. Original: (fvg_high, fvg_low, fvg_direction, swing_level, swing_type, post_swing_candles_df, instrument)
    2. Scanner: (df, swing_level, direction, instrument) - detected if args[0] is DataFrame
    """
    if len(args) > 0 and isinstance(args[0], pd.DataFrame):
        # --- SCANNER PATTERN: (df, swing_level, direction, instrument) ---
        df, swing_level, direction, instrument = args
        
        # We need to find where the level was swept
        # Looking at recent candles (last 10)
        recent_df = df.tail(10)
        sweep_found = False
        sweep_idx = -1
        
        for i in range(len(recent_df)):
            row = recent_df.iloc[i]
            if direction == 'BULLISH':
                if row['low'] < swing_level and row['close'] > swing_level:
                    sweep_found = True
                    sweep_idx = i
                    break
            else:
                if row['high'] > swing_level and row['close'] < swing_level:
                    sweep_found = True
                    sweep_idx = i
                    break
                    
        if not sweep_found:
            return {"is_ofl_sweep": False}
            
        post_sweep_df = recent_df.iloc[sweep_idx:]
        # Find continuation FVG
        fvgs = scan_candles_for_fvgs(df.tail(20), instrument)
        continuation = next((f for f in fvgs if f['direction'] == direction), None)
        
        return {
            "is_ofl_sweep": True,
            "continuation_fvg": continuation,
            "continuation_fvg_high": continuation['fvg_high'] if continuation else None,
            "continuation_fvg_low": continuation['fvg_low'] if continuation else None,
            "sweep_type": "ORDER_FLOW_SWEEP",
            "swept_level": swing_level
        }
    
    # --- ORIGINAL PATTERN: (fvg_high, fvg_low, fvg_direction, swing_level, swing_type, post_swing_candles_df, instrument) ---
    if len(args) < 6:
        return {"is_ofl_sweep": False}
        
    fvg_high, fvg_low, fvg_direction, swing_level, swing_type, post_swing_candles_df, instrument = args[:7]
    
    # First candle in post_swing_candles_df is the sweep candidate
    if len(post_swing_candles_df) < 1:
        return {"is_ofl_sweep": False, "sweep_details": None, "continuation_fvg": None}
        
    c_sweep = post_swing_candles_df.iloc[0]
    next_df = post_swing_candles_df.iloc[1:]
    
    classification = classify_liquidity_event(
        swing_level, "ORDER_FLOW_SWEEP", 
        c_sweep['high'], c_sweep['low'], c_sweep['close'], 
        next_df, instrument
    )
    
    if classification['event'] == "SWEEP":
        # Find continuation FVG in next_df
        fvgs = scan_candles_for_fvgs(post_swing_candles_df, instrument)
        # Look for FVG in correct direction (same as fvg_direction)
        continuation = next((f for f in fvgs if f['direction'] == fvg_direction), None)
        
        return {
            "is_ofl_sweep": True,
            "sweep_details": classification,
            "continuation_fvg": continuation,
            "continuation_fvg_high": continuation['fvg_high'] if continuation else None,
            "continuation_fvg_low": continuation['fvg_low'] if continuation else None,
            "sweep_type": "ORDER_FLOW_SWEEP",
            "swept_level": swing_level
        }
        
    return {"is_ofl_sweep": False, "sweep_details": classification, "continuation_fvg": None}

def detect_candle_science_sweep(candle_df, context_fvg_high, context_fvg_low, direction, instrument):
    # CS sweep: Previous candle high (PCH) or low (PCL) swept after context entry
    # Requires candle_df (at least 2 candles)
    if len(candle_df) < 2:
        return {"is_cs_sweep": False, "swept_level": None}
        
    c1 = candle_df.iloc[0]
    c2 = candle_df.iloc[1]
    
    is_cs = False
    swept_level = None
    
    if direction == "BEARISH": # Enter FVG from below? Rejection at PCH
        # Bearish context: price enters zone, c1 doesn't rejection, c2 sweeps c1.high
        if c2['high'] > c1['high'] and c2['close'] < c1['high']:
            is_cs = True
            swept_level = c1['high']
    else: # BULLISH
        if c2['low'] < c1['low'] and c2['close'] > c1['low']:
            is_cs = True
            swept_level = c1['low']
            
    if is_cs:
        # Check next for continuation
        next_fvgs = scan_candles_for_fvgs(candle_df, instrument)
        return {
            "is_cs_sweep": True, 
            "swept_level": swept_level,
            "continuation_fvg": next_fvgs[0] if next_fvgs else None
        }
        
    return {"is_cs_sweep": False, "swept_level": None}

def calculate_sweep_probability(liquidity_event, sweep_type, wick_size_pips, instrument, is_aggressive, has_continuation_fvg, comfortable_candles):
    if liquidity_event == "RUN":
        return {"probability_score": 0.0, "probability_label": "LOW", "breakdown": "Liquidity event was a RUN (trend), not a sweep"}
        
    base_score = SWEEP_PROBABILITY_BASE
    breakdown = [f"Base probability for {liquidity_event}: {base_score}"]
    
    if is_aggressive:
        base_score -= AGGRESSIVE_PENALTY
        breakdown.append(f"Aggressive continuation penalty: -{AGGRESSIVE_PENALTY}")
        
    if has_continuation_fvg:
        base_score += ORDER_FLOW_SWEEP_BONUS
        breakdown.append(f"Continuation FVG bonus: +{ORDER_FLOW_SWEEP_BONUS}")
        
    if comfortable_candles == 0:
        base_score += 10
        breakdown.append("Immediate reversal bonus: +10")
    elif comfortable_candles == 1:
        base_score += 5
        breakdown.append("Fast reversal bonus: +5")
        
    min_wick = SWEEP_WICK_MIN_PIPS.get(instrument, 2.0)
    if wick_size_pips < min_wick:
        base_score -= 15
        breakdown.append(f"Weak wick penalty (below {min_wick} pips): -15")
    elif wick_size_pips > min_wick * 3:
        base_score += 10
        breakdown.append(f"Strong wick bonus (above {min_wick*3} pips): +10")
        
    if sweep_type == "ORDER_FLOW_SWEEP":
        base_score += ORDER_FLOW_SWEEP_BONUS
        breakdown.append(f"Order Flow Sweep bonus: +{ORDER_FLOW_SWEEP_BONUS}")
    elif sweep_type == "CANDLE_SCIENCE_SWEEP":
        base_score += CS_SWEEP_BONUS
        breakdown.append(f"Candle Science Sweep bonus: +{CS_SWEEP_BONUS}")
        
    final_score = max(0.0, min(100.0, base_score))
    label = "LOW"
    if final_score >= 70: label = "HIGH"
    elif final_score >= 45: label = "MEDIUM"
    
    return {
        "probability_score": round(float(final_score), 2),
        "probability_label": label,
        "breakdown": " | ".join(breakdown)
    }

def find_target_after_sweep(swept_level, sweep_direction, swing_list, fvg_list, instrument):
    target_price = None
    target_type = None
    
    if sweep_direction == "BULLISH": # Swept lows, target is ABOVE
        # Nearest Swing High or Bearish FVG
        options = []
        for s in swing_list:
            if s['swing_type'] == "SWING_HIGH" and s['swing_level'] > swept_level:
                options.append((s['swing_level'], "SWING_HIGH"))
        for f in fvg_list:
            if f['direction'] == "BEARISH" and f['fvg_low'] > swept_level:
                options.append((f['fvg_low'], "BEARISH_FVG"))
        
        if options:
            options.sort(key=lambda x: x[0]) # Closest one above
            target_price, target_type = options[0]
            
    else: # BEARISH: Swept highs, target is BELOW
        options = []
        for s in swing_list:
            if s['swing_type'] == "SWING_LOW" and s['swing_level'] < swept_level:
                options.append((s['swing_level'], "SWING_LOW"))
        for f in fvg_list:
            if f['direction'] == "BULLISH" and f['fvg_high'] < swept_level:
                options.append((f['fvg_high'], "BULLISH_FVG"))
                
        if options:
            options.sort(key=lambda x: x[0], reverse=True) # Closest one below
            target_price, target_type = options[0]
            
    if target_price:
        pip_mult = get_pip_multiplier(instrument)
        distance = abs(target_price - swept_level) * pip_mult
        return {
            "target_price": target_price,
            "target_type": target_type,
            "distance_pips": round(float(distance), 2)
        }
    return None

def analyze_sweep(instrument, timeframe, candle_index, df, swing_list, fvg_list):
    if candle_index >= len(df) - 1: return None
    
    c = df.iloc[candle_index]
    # Next 5 candles for comfort check
    next_df = df.iloc[candle_index+1 : candle_index+6]
    
    # Optimized: only check the last 50 swings to avoid O(N^2)
    search_swings = swing_list[-50:] if len(swing_list) > 50 else swing_list
    
    # Check against recent unmitigated swings
    for s in reversed(search_swings):
        if s.get('is_mitigated', False): continue
        
        # Only check swings created BEFORE this candle
        # Note: both are strings in 'YYYY-MM-DD HH:MM:SS' format, direct comparison works
        if s['datetime'] >= c['datetime']: continue
        
        swept_level = s['swing_level']
        direction = "BULLISH" if s['swing_type'] == "SWING_LOW" else "BEARISH"
        
        event_res = classify_liquidity_event(
            swept_level, s['swing_type'], 
            c['high'], c['low'], c['close'], 
            next_df, instrument
        )
        
        if event_res['event'] == "SWEEP":
            pip_mult = get_pip_multiplier(instrument)
            wick_size = 0
            if direction == "BULLISH":
                wick_size = swept_level - c['low']
            else:
                wick_size = c['high'] - swept_level
            
            wick_pips = wick_size * pip_mult
            
            # Simplified sweep_type detection
            sweep_type = "TURTLE_SOUP" # Default
            # More logic needed to distinguish OFL vs CS based on context
            
            target = find_target_after_sweep(swept_level, direction, swing_list, fvg_list, instrument)
            
            # Check for continuation FVG in next 5 candles
            fvgs_after = scan_candles_for_fvgs(next_df, instrument)
            cont_fvg = next((f for f in fvgs_after if f['direction'] == direction), None)
            
            prob = calculate_sweep_probability(
                "SWEEP", sweep_type, wick_pips, instrument, 
                event_res['is_aggressive'], cont_fvg is not None, 
                event_res['comfortable_candles']
            )
            
            return {
                "instrument": instrument,
                "timeframe": timeframe,
                "sweep_type": sweep_type,
                "sweep_direction": direction,
                "swept_level": swept_level,
                "sweep_candle_high": c['high'],
                "sweep_candle_low": c['low'],
                "sweep_candle_close": c['close'],
                "wick_size_pips": round(float(wick_pips), 2),
                "is_aggressive": event_res['is_aggressive'],
                "comfortable_candles": event_res['comfortable_candles'],
                "liquidity_event": "SWEEP",
                "continuation_fvg_high": cont_fvg['fvg_high'] if cont_fvg else None,
                "continuation_fvg_low": cont_fvg['fvg_low'] if cont_fvg else None,
                "swing_point_id": s.get('id'),
                "target_after_sweep": target['target_price'] if target else None,
                "probability_score": prob['probability_score'],
                "trade_date": c['datetime'],
                "notes": prob['breakdown']
            }
            
    return None

def scan_candles_for_sweeps(instrument, timeframe):
    df = fetch_candles(instrument, timeframe)
    swings = scan_candles_for_swings(df)
    fvgs = scan_candles_for_fvgs(df, instrument)
    
    results = []
    # Only scan last 100 candles for performance
    start_idx = max(0, len(df) - 100)
    for i in range(start_idx, len(df)):
        sweep = analyze_sweep(instrument, timeframe, i, df, swings, fvgs)
        if sweep:
            results.append(sweep)
            
    results.sort(key=lambda x: x['trade_date'], reverse=True)
    return results

def get_sweep_vs_run_summary(instrument, timeframe):
    all_sweeps = scan_candles_for_sweeps(instrument, timeframe)
    if not all_sweeps:
        return {"total_events": 0, "total_sweeps": 0, "total_runs": 0, "accuracy": 0}
        
    runs = 0 # In a real system we'd scan for runs too
    sweeps = len(all_sweeps)
    
    bullish = len([s for s in all_sweeps if s['sweep_direction'] == "BULLISH"])
    bearish = len([s for s in all_sweeps if s['sweep_direction'] == "BEARISH"])
    
    return {
        "total_events": sweeps + runs,
        "total_sweeps": sweeps,
        "total_runs": runs,
        "sweep_accuracy": 100.0, # Placeholder
        "most_recent_event": all_sweeps[0] if all_sweeps else None,
        "by_direction": {"BULLISH": bullish, "BEARISH": bearish}
    }

from functools import lru_cache
from modules.data_engine import fetch_candles, BACKTEST_MODE, BACKTEST_END_DATE

@lru_cache(maxsize=1024)
def _cached_full_sweep_scan(instrument, timeframe, context_date):
    sweeps = scan_candles_for_sweeps(instrument, timeframe)
    summary = get_sweep_vs_run_summary(instrument, timeframe)
    
    high_prob = [s for s in sweeps if s['probability_score'] >= 70]
    
    return {
        "instrument": instrument,
        "timeframe": timeframe,
        "total_sweeps": len(sweeps),
        "high_prob_sweeps": len(high_prob),
        "all_sweeps": sweeps,
        "summary": summary
    }

def full_sweep_scan(instrument: str, timeframe: str, context_date: str = None) :
    """
    Performs full sweep scanning. In backtest mode, it uses the global context for caching.
    """
    if context_date is None and BACKTEST_MODE:
        context_date = BACKTEST_END_DATE
    
    if context_date is None:
        context_date = "LIVE"
        
    return _cached_full_sweep_scan(instrument, timeframe, context_date)

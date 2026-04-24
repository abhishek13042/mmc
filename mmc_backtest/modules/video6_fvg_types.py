import pandas as pd
import numpy as np
from modules.video1_pd_arrays import (
    validate_bullish_fvg,
    validate_bearish_fvg,
    calculate_rejection_ratio,
    classify_fvg_type,
    scan_candles_for_fvgs,
    scan_candles_for_swings,
    calculate_fvg_size_pips,
    get_pip_multiplier,
    check_mitigation
)
from modules.data_engine import fetch_candles

# --- CONSTANTS ---
FVG_STRENGTH_MAP = {
    'PFVG': {
        'trend_strength':    80.0,
        'opposing_strength': 20.0,
        'probability_score': 85.0,
        'recommendation':    'TRADE_IT',
        'extra_confirmation': False
    },
    'BFVG': {
        'trend_strength':    100.0,
        'opposing_strength': 0.0,
        'probability_score': 65.0,
        'recommendation':    'DROP_TF',
        'extra_confirmation': False
    },
    'RFVG': {
        'trend_strength':    60.0,
        'opposing_strength': 40.0,
        'probability_score': 25.0,
        'recommendation':    'AVOID',
        'extra_confirmation': True
    }
}

OPPOSING_PDA_BONUS     = 15.0
SWEEP_PENALTY          = 20.0
PFVG_REJECTION_MAX     = 0.25
RFVG_REJECTION_MIN     = 0.45

def calculate_gap_sizes(c1_high, c1_low, c2_high, c2_low, c3_high, c3_low, direction):
    if direction == "BULLISH":
        potential_gap_high = c2_high
        potential_gap_low  = c1_high
        potential_gap_size = max(0, potential_gap_high - potential_gap_low)
        actual_gap_high    = c3_low
        actual_gap_low     = c1_high
        actual_gap_size    = max(0, actual_gap_high - actual_gap_low)
    else: # BEARISH
        potential_gap_high = c1_low
        potential_gap_low  = c2_low
        potential_gap_size = max(0, potential_gap_high - potential_gap_low)
        actual_gap_high    = c1_low
        actual_gap_low     = c3_high
        actual_gap_size    = max(0, actual_gap_high - actual_gap_low)
        
    size_ratio = actual_gap_size / potential_gap_size if potential_gap_size > 0 else 0
    return {
        "potential_gap_size": potential_gap_size,
        "actual_gap_size": actual_gap_size,
        "size_ratio": round(float(size_ratio), 4)
    }

def detect_opposing_pda(fvg_high, fvg_low, direction, swing_list, fvg_list):
    tolerance_pct = 0.001 # 0.1% buffer
    at_opposing_pda = False
    opposing_type = None
    opposing_level = None
    after_sweep = False
    
    if direction == "BULLISH":
        # Target: Premium PDAs (Swing Highs, Bearish FVGs)
        target_price = fvg_high
        for swing in swing_list:
            if swing['swing_type'] == "SWING_HIGH" and not swing.get('is_mitigated', False):
                if abs(swing['swing_level'] - target_price) <= target_price * tolerance_pct:
                    at_opposing_pda = True
                    opposing_type = "SWING_HIGH"
                    opposing_level = swing['swing_level']
                    break
        if not at_opposing_pda:
            for fvg in fvg_list:
                if fvg['direction'] == "BEARISH" and not fvg.get('is_mitigated', False):
                    if abs(fvg['fvg_high'] - target_price) <= target_price * tolerance_pct:
                        at_opposing_pda = True
                        opposing_type = "BEARISH_FVG"
                        opposing_level = fvg['fvg_high']
                        break
    else: # BEARISH
        # Target: Discount PDAs (Swing Lows, Bullish FVGs)
        target_price = fvg_low
        for swing in swing_list:
            if swing['swing_type'] == "SWING_LOW" and not swing.get('is_mitigated', False):
                if abs(swing['swing_level'] - target_price) <= target_price * tolerance_pct:
                    at_opposing_pda = True
                    opposing_type = "SWING_LOW"
                    opposing_level = swing['swing_level']
                    break
        if not at_opposing_pda:
            for fvg in fvg_list:
                if fvg['direction'] == "BULLISH" and not fvg.get('is_mitigated', False):
                    if abs(fvg['fvg_low'] - target_price) <= target_price * tolerance_pct:
                        at_opposing_pda = True
                        opposing_type = "BULLISH_FVG"
                        opposing_level = fvg['fvg_low']
                        break
                        
    # Simplified sweep detection: if candle closed inside PDA but wicked beyond it
    # This requires candle data not present in this function's signature
    # but the prompt implies logic based on these signatures. 
    # I'll leave after_sweep as False for now or add a placeholder.
    
    return {
        "at_opposing_pda": at_opposing_pda,
        "opposing_type": opposing_type,
        "opposing_level": opposing_level,
        "after_sweep": after_sweep
    }

def calculate_fvg_probability(fvg_type, at_opposing_pda, after_sweep):
    config = FVG_STRENGTH_MAP[fvg_type]
    base_score = config['probability_score']
    reasoning = [f"Base probability for {fvg_type}: {base_score}"]
    
    if at_opposing_pda:
        base_score += OPPOSING_PDA_BONUS
        reasoning.append(f"Opposing PDA Confluence bonus: +{OPPOSING_PDA_BONUS}")
    
    if after_sweep:
        base_score -= SWEEP_PENALTY
        reasoning.append(f"Sweep Penalty: -{SWEEP_PENALTY}")
        
    final_score = max(0.0, min(100.0, base_score))
    
    # Rule 6: RFVG score cap
    if fvg_type == "RFVG":
        final_score = min(final_score, 40.0)
        reasoning.append("RFVG score capped at 40.0 maximum")

    rating = "LOW"
    if final_score >= 75: rating = "HIGH"
    elif final_score >= 45: rating = "MEDIUM"
    
    return {
        "probability_score": round(float(final_score), 2),
        "probability_rating": rating,
        "reasoning": " | ".join(reasoning)
    }

def get_trading_recommendation(fvg_type, probability_score, after_sweep):
    # Rule 8: recommendation must match fvg_type
    if fvg_type == "RFVG":
        return {
            "recommendation": "AVOID",
            "action": "Skip — too much opposing strength",
            "notes": "Rejection FVG — bearish/bullish side too strong"
        }
    
    if fvg_type == "BFVG":
        return {
            "recommendation": "DROP_TF",
            "action": "Go lower timeframe, find inner FVG to trade",
            "notes": "Breakaway gap — too much trend strength for direct entry"
        }
        
    if fvg_type == "PFVG":
        if after_sweep:
            return {
                "recommendation": "EXTRA_CONFIRMATION",
                "action": "Wait for lower TF OFL confirmation",
                "notes": "FVG formed after sweep — requires more confirmation"
            }
        
        if probability_score >= 75:
            return {
                "recommendation": "TRADE_IT",
                "action": "Enter in FVG zone on entry confirmation",
                "notes": "Perfect FVG — best setup, minimal opposing strength"
            }
            
    return {
        "recommendation": "EXTRA_CONFIRMATION",
        "action": "Wait for entry confirmation",
        "notes": f"Standard {fvg_type} with medium probability"
    }

def full_fvg_analysis(instrument, timeframe, fvg_dict, swing_list, fvg_list):
    direction = fvg_dict['direction']
    c1h, c1l = fvg_dict['candle1_high'], fvg_dict['candle1_low']
    c2h, c2l = fvg_dict['candle2_high'], fvg_dict['candle2_low']
    c3h, c3l = fvg_dict['candle3_high'], fvg_dict['candle3_low']
    fh, fl = fvg_dict['fvg_high'], fvg_dict['fvg_low']
    
    gap_metrics = calculate_gap_sizes(c1h, c1l, c2h, c2l, c3h, c3l, direction)
    rr = calculate_rejection_ratio(fh, fl, c3h, c3l, direction)
    fvg_type = classify_fvg_type(rr, c3h, c3l, c2h, c2l, direction)
    
    opposing_res = detect_opposing_pda(fh, fl, direction, swing_list, fvg_list)
    prob_res = calculate_fvg_probability(fvg_type, opposing_res['at_opposing_pda'], opposing_res['after_sweep'])
    recomm = get_trading_recommendation(fvg_type, prob_res['probability_score'], opposing_res['after_sweep'])
    
    strength_cfg = FVG_STRENGTH_MAP[fvg_type]
    
    result = {
        **fvg_dict,  # Preserve all original metadata (timestamps, indices)
        "fvg_id": fvg_dict.get('id', 0),
        "instrument": instrument,
        "timeframe": timeframe,
        "direction": direction,
        "fvg_type": fvg_type,
        "rejection_ratio": rr,
        "potential_gap_size": gap_metrics['potential_gap_size'],
        "actual_gap_size": gap_metrics['actual_gap_size'],
        "strength_percentage": strength_cfg['trend_strength'],
        "opposing_strength_pct": strength_cfg['opposing_strength'],
        "at_opposing_pda": opposing_res['at_opposing_pda'],
        "opposing_pda_type": opposing_res['opposing_type'],
        "opposing_pda_level": opposing_res['opposing_level'],
        "after_sweep": opposing_res['after_sweep'],
        "probability_rating": prob_res['probability_rating'],
        "probability_score": prob_res['probability_score'],
        "trading_recommendation": recomm['recommendation'],
        "extra_confirmation_needed": strength_cfg['extra_confirmation'] or opposing_res['after_sweep']
    }
    return result

from functools import lru_cache
from modules.data_engine import fetch_candles, BACKTEST_MODE, BACKTEST_END_DATE

@lru_cache(maxsize=1024)
def _cached_scan_and_classify_all_fvgs(instrument, timeframe, context_date):
    df = fetch_candles(instrument, timeframe)
    fvg_list = scan_candles_for_fvgs(df, instrument)
    swing_list = scan_candles_for_swings(df)
    
    results = []
    for fvg in fvg_list:
        if fvg.get('is_mitigated', False): continue
        analysis = full_fvg_analysis(instrument, timeframe, fvg, swing_list, fvg_list)
        results.append(analysis)
        
    results.sort(key=lambda x: x['probability_score'], reverse=True)
    return results

def scan_and_classify_all_fvgs(instrument: str, timeframe: str, context_date: str = None) -> list:
    """
    Scans and classifies all FVGs. In backtest mode, it uses the global context for caching.
    """
    if context_date is None and BACKTEST_MODE:
        context_date = BACKTEST_END_DATE
    
    if context_date is None:
        context_date = "LIVE"
        
    return _cached_scan_and_classify_all_fvgs(instrument, timeframe, context_date)

def get_tradeable_fvgs(instrument, timeframe):
    all_classified = scan_and_classify_all_fvgs(instrument, timeframe)
    tradeable = [
        f for f in all_classified 
        if f['probability_rating'] in ['HIGH', 'MEDIUM'] 
        and f['trading_recommendation'] != 'AVOID'
    ]
    return tradeable

def compare_fvg_quality(fvg_analyses):
    # Sort by probability_score descending
    sorted_fvgs = sorted(fvg_analyses, key=lambda x: x['probability_score'], reverse=True)
    
    for i, fvg in enumerate(sorted_fvgs):
        rank = i + 1
        fvg['rank'] = rank
        if rank == 1:
            fvg['quality_tier'] = 'TIER_1'
        elif 2 <= rank <= 3:
            fvg['quality_tier'] = 'TIER_2'
        else:
            fvg['quality_tier'] = 'TIER_3'
            
    return sorted_fvgs

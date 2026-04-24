import pandas as pd
import numpy as np
from modules.video1_pd_arrays import (
    scan_candles_for_fvgs,
    scan_candles_for_swings,
    calculate_fvg_size_pips,
    get_pip_multiplier,
    check_mitigation
)
from modules.video2_market_structure import (
    scan_it_points,
    calculate_fva_boundaries,
    detect_overlapping_fvg,
    detect_nested_fva,
    fair_value_theory_check,
    classify_fva_type,
    detect_sweep_at_fva
)
from modules.video6_fvg_types import (
    full_fvg_analysis,
    calculate_fvg_probability
)
from modules.data_engine import fetch_candles

# --- CONSTANTS ---
FVA_BASE_SCORES = {
    'IDEAL': 90.0,
    'GOOD':  70.0,
    'WEAK':  20.0
}

OVERLAP_FVG_BONUSES = {
    'PFVG': 10.0,
    'BFVG': 5.0,
    'RFVG': 0.0
}

NESTED_FVA_BONUS    = 8.0
SWEEP_PENALTY       = 25.0

PROBABILITY_ARRAYS_MAP = {
    'IDEAL': 3,
    'GOOD':  2,
    'WEAK':  1
}

TOLERANCE_PCT = 0.001

def measure_sweep_wick(candle_high, candle_low, candle_close, swing_level, direction, instrument):
    is_sweep = False
    wick_size = 0
    total_range = candle_high - candle_low
    
    if direction == "BULLISH": # Price wicked above swing high
        if candle_high > swing_level and candle_close < swing_level:
            is_sweep = True
            wick_size = candle_high - swing_level
    else: # BEARISH: Price wicked below swing low
        if candle_low < swing_level and candle_close > swing_level:
            is_sweep = True
            wick_size = swing_level - candle_low
            
    pip_mult = get_pip_multiplier(instrument)
    wick_size_pips = wick_size * pip_mult
    wick_ratio = wick_size / total_range if total_range > 0 else 0
    
    return {
        "is_sweep": is_sweep,
        "wick_size_pips": round(float(wick_size_pips), 2),
        "wick_ratio": round(float(wick_ratio), 4)
    }

def find_overlapping_fvg_detailed(fva_high, fva_low, fvg_list, direction):
    tolerance = fva_high * TOLERANCE_PCT
    
    for fvg in fvg_list:
        if fvg.get("is_mitigated", False): continue
        if direction == "BULLISH" and fvg["direction"] != "BULLISH": continue
        if direction == "BEARISH" and fvg["direction"] != "BEARISH": continue
        
        overlap = False
        if direction == "BULLISH":
            # BULLISH FVA — look for BULLISH FVG overlapping fva_low
            if fvg["fvg_high"] >= fva_low - tolerance and fvg["fvg_low"] <= fva_low + tolerance:
                overlap = True
        else: # BEARISH
            # BEARISH FVA — look for BEARISH FVG overlapping fva_high
            if fvg["fvg_low"] <= fva_high + tolerance and fvg["fvg_high"] >= fva_high - tolerance:
                overlap = True
                
        if overlap:
            overlap_zone_high = min(fvg["fvg_high"], fva_high)
            overlap_zone_low  = max(fvg["fvg_low"], fva_low)
            overlap_size = overlap_zone_high - overlap_zone_low
            
            ft = fvg.get("fvg_type", "PFVG")
            quality = "LOW"
            if ft == "PFVG": quality = "HIGH"
            elif ft == "BFVG": quality = "MEDIUM"
            
            return {
                "has_overlap": True,
                "fvg_high": fvg["fvg_high"],
                "fvg_low": fvg["fvg_low"],
                "fvg_type": ft,
                "overlap_zone_high": overlap_zone_high,
                "overlap_zone_low": overlap_zone_low,
                "overlap_size": overlap_size,
                "overlap_quality": quality
            }
            
    return {
        "has_overlap": False, "fvg_high": None, "fvg_low": None, 
        "fvg_type": None, "overlap_zone_high": None, "overlap_zone_low": None,
        "overlap_size": 0, "overlap_quality": "NONE"
    }

def find_nested_fva_detailed(fva_high, fva_low, it_points_list, instrument):
    # BULLISH nested: IT High < fva_high and > fva_low; IT Low > fva_low and < fva_high
    # Find all pairs
    it_highs = [p for p in it_points_list if p["point_type"] == "IT_HIGH" and fva_low < p["price_level"] < fva_high]
    it_lows = [p for p in it_points_list if p["point_type"] == "IT_LOW" and fva_low < p["price_level"] < fva_high]
    
    if not it_highs or not it_lows:
        return {"has_nested": False, "nested_high": None, "nested_low": None, "nested_size_pips": 0, "nested_position": None}
        
    # Innermost = smallest spread or closest to low for bullish? Prompt: "INNERMOST nested FVA (closest to fva_low for bullish)"
    it_highs.sort(key=lambda x: x["price_level"])
    it_lows.sort(key=lambda x: x["price_level"])
    
    nested_high = it_highs[0]["price_level"]
    nested_low = it_lows[-1]["price_level"] # highest low
    
    if nested_high <= nested_low:
        return {"has_nested": False, "nested_high": None, "nested_low": None, "nested_size_pips": 0, "nested_position": None}
        
    pip_mult = get_pip_multiplier(instrument)
    size_pips = (nested_high - nested_low) * pip_mult
    
    fva_range = fva_high - fva_low
    pos = "MIDDLE_THIRD"
    if nested_high > fva_high - (fva_range/3): pos = "UPPER_THIRD"
    elif nested_low < fva_low + (fva_range/3): pos = "LOWER_THIRD"
    
    return {
        "has_nested": True,
        "nested_high": nested_high,
        "nested_low": nested_low,
        "nested_size_pips": round(float(size_pips), 2),
        "nested_position": pos
    }

def calculate_fva_probability(fva_type, overlap_quality, has_nested, is_sweep):
    base_score = FVA_BASE_SCORES.get(fva_type, 20.0)
    overlap_bonus = OVERLAP_FVG_BONUSES.get(overlap_quality, 0)
    nested_bonus = NESTED_FVA_BONUS if has_nested else 0
    sweep_penalty = SWEEP_PENALTY if is_sweep else 0
    
    final_score = base_score + overlap_bonus + nested_bonus - sweep_penalty
    final_score = max(0.0, min(100.0, final_score))
    
    # Rule 4: Weak FVA cap
    if fva_type == "WEAK":
        final_score = min(final_score, 40.0)
        
    label = "LOW"
    if final_score >= 75: label = "HIGH"
    elif final_score >= 45: label = "MEDIUM"
    
    return {
        "probability_score": round(float(final_score), 2),
        "probability_label": label,
        "probability_arrays": PROBABILITY_ARRAYS_MAP.get(fva_type, 1),
        "breakdown": {
            "base_score": base_score,
            "overlap_bonus": overlap_bonus,
            "nested_bonus": nested_bonus,
            "sweep_penalty": sweep_penalty,
            "final_score": final_score
        }
    }

def get_fva_trading_recommendation(fva_type, probability_label, is_sweep, has_nested):
    if is_sweep and fva_type == "WEAK":
        return {
            "recommendation": "AVOID",
            "entry_zone": None,
            "notes": "Sweep of opposing PDA — lack of strength, avoid"
        }
        
    if fva_type == "WEAK":
        return {
            "recommendation": "TRADE_FROM_FVG_ONLY",
            "entry_zone": "overlapping FVG zone",
            "notes": "Weak FVA — only trade from FVG inside if present"
        }
        
    if fva_type == "GOOD":
        return {
            "recommendation": "TRADE_FROM_FVA",
            "entry_zone": "FVA boundary zone",
            "notes": "Good FVA — trade from FVA + FVG overlap zone"
        }
        
    if fva_type == "IDEAL":
        if has_nested:
            return {
                "recommendation": "TRADE_FROM_NESTED",
                "entry_zone": "nested FVA zone",
                "notes": "Ideal FVA — use nested FVA as precision entry zone"
            }
        else:
            return {
                "recommendation": "TRADE_FROM_FVA",
                "entry_zone": "FVA boundary zone",
                "notes": "Ideal FVA — trade from main FVA zone"
            }
            
    return {"recommendation": "UNKNOWN", "entry_zone": None, "notes": "Undefined FVA type"}

def assess_market_state_at_fva(current_price, fva_high, fva_low, direction):
    # Rule 7: Always return OFFERING_FAIR_VALUE or SEEKING_LIQUIDITY
    theory = fair_value_theory_check(current_price, fva_high, fva_low, direction)
    
    state_map = {
        "OFFERING_FAIR_VALUE": {
            "action": "Slow retracement into FVA, then continuation with fair value gaps",
            "theory": "Market offering both buyers and sellers a fair chance — retracement is normal",
            "retracement": True
        },
        "SEEKING_LIQUIDITY": {
            "action": "Fast move toward swing point (LOD), bypassing FVA entirely",
            "theory": "Market not offering fair value — hunting liquidity at swing point",
            "retracement": True
        },
        "BEYOND_FVA": {
            "action": "Fast price action, minimal retracement, only FVG stings allowed",
            "theory": "Area is already fair value — no reason for deep retracement",
            "retracement": False
        }
    }
    
    cfg = state_map.get(theory["state"])
    return {
        "state": theory["state"],
        "price_action_expected": cfg["action"],
        "fair_value_theory": cfg["theory"],
        "retracement_expected": cfg["retracement"]
    }

def detect_fast_price_action_zone(fva_high, fva_low, swing_target, direction):
    if direction == "BULLISH":
        return {
            "fast_zone_start": fva_high,
            "fast_zone_end": swing_target,
            "reason": "Area is already fair value — fast continuation expected"
        }
    else: # BEARISH
        return {
            "fast_zone_start": fva_low,
            "fast_zone_end": swing_target,
            "reason": "Area is already fair value — fast continuation expected"
        }

def full_fva_analysis(instrument, timeframe, fva_dict, fvg_list, it_points, current_price):
    fh, fl = fva_dict["fva_high"], fva_dict["fva_low"]
    direction = fva_dict["direction"]
    
    overlap = find_overlapping_fvg_detailed(fh, fl, fvg_list, direction)
    nested = find_nested_fva_detailed(fh, fl, it_points, instrument)
    
    is_sweep = fva_dict.get("is_sweep", False)
    
    # Rule 1: IDEAL requires ALL 3
    final_type = classify_fva_type(overlap["has_overlap"], nested["has_nested"], is_sweep)
    
    prob = calculate_fva_probability(final_type, overlap["overlap_quality"], nested["has_nested"], is_sweep)
    recomm = get_fva_trading_recommendation(final_type, prob["probability_label"], is_sweep, nested["has_nested"])
    state = assess_market_state_at_fva(current_price, fh, fl, direction)
    
    size_pips = (fh - fl) * get_pip_multiplier(instrument)
    
    return {
        "fva_id": fva_dict.get("id", 0),
        "instrument": instrument,
        "timeframe": timeframe,
        "fva_type": final_type,
        "fva_high": fh,
        "fva_low": fl,
        "fva_size_pips": round(float(size_pips), 2),
        "swing_point_taken": fva_dict.get("swing_point_taken", 0),
        "has_overlapping_fvg": overlap["has_overlap"],
        "overlapping_fvg_high": overlap["fvg_high"],
        "overlapping_fvg_low": overlap["fvg_low"],
        "overlapping_fvg_type": overlap["fvg_type"],
        "overlap_quality": overlap["overlap_quality"],
        "has_nested_fva": nested["has_nested"],
        "nested_fva_high": nested["nested_high"],
        "nested_fva_low": nested["nested_low"],
        "nested_fva_size_pips": nested["nested_size_pips"],
        "is_sweep": is_sweep,
        "sweep_wick_size": 0, # Should be measured from candles if provided
        "probability_arrays": prob["probability_arrays"],
        "probability_score": prob["probability_score"],
        "probability_label": prob["probability_label"],
        "market_state": state["state"],
        "retracement_expected": state["retracement_expected"],
        "trading_recommendation": recomm["recommendation"]
    }

def scan_and_classify_all_fvas(instrument, timeframe):
    df = fetch_candles(instrument, timeframe)
    fvg_list = scan_candles_for_fvgs(df, instrument)
    it_points = scan_it_points(df)
    
    # FVA logic: price between previous IT High and IT Low after one is taken
    # Simplified builder for scan: find recent pairs
    it_highs = sorted([p for p in it_points if p["point_type"] == "IT_HIGH"], key=lambda x: x["datetime"])
    it_lows = sorted([p for p in it_points if p["point_type"] == "IT_LOW"], key=lambda x: x["datetime"])
    
    results = []
    current_price = df.iloc[-1]["close"]
    
    if len(it_highs) >= 1 and len(it_lows) >= 1:
        # For simplicity, build most recent
        fh, fl = it_highs[-1]["price_level"], it_lows[-1]["price_level"]
        direction = "BULLISH" # Simplified: find if high or low was taken last
        
        fva_dict = {
            "fva_high": fh, "fva_low": fl, "direction": direction, 
            "is_sweep": False, "swing_point_taken": fl
        }
        
        analysis = full_fva_analysis(instrument, timeframe, fva_dict, fvg_list, it_points, current_price)
        results.append(analysis)
        
    return results

def get_tradeable_fvas(instrument, timeframe):
    all_fvas = scan_and_classify_all_fvas(instrument, timeframe)
    return [
        f for f in all_fvas 
        if f["probability_label"] in ["HIGH", "MEDIUM"] 
        and f["trading_recommendation"] != "AVOID"
    ]

def compare_fva_strength(fva_list):
    for f in fva_list:
        score = f["probability_score"]
        if f["has_overlapping_fvg"]: score += 10
        if f["has_nested_fva"]: score += 8
        if f["is_sweep"]: score -= 25
        f["strength_score"] = score
        
    sorted_fvas = sorted(fva_list, key=lambda x: x["strength_score"], reverse=True)
    for i, f in enumerate(sorted_fvas):
        f["rank"] = i + 1
        sc = f["strength_score"]
        if sc >= 80: f["strength_tier"] = "TIER_1"
        elif sc >= 50: f["strength_tier"] = "TIER_2"
        else: f["strength_tier"] = "TIER_3"
        
    return sorted_fvas

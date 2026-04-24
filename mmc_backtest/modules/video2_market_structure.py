import pandas as pd
import numpy as np
from modules.video1_pd_arrays import (
    validate_swing_high,
    validate_swing_low,
    scan_candles_for_swings,
    scan_candles_for_fvgs,
    calculate_fvg_size_pips,
    check_mitigation,
    get_pip_multiplier
)
from modules.data_engine import fetch_candles

# --- CONSTANTS ---
TIMEFRAME_HIERARCHY = [
    "MONTHLY", "WEEKLY", "DAILY", "4H", "1H", "15M", "5M", "1M"
]

def classify_it_point(swing_level, swing_type, left_swing_level, right_swing_level):
    if swing_type == "SWING_HIGH":
        if left_swing_level < swing_level and right_swing_level < swing_level:
            return {
                "is_it": True,
                "point_type": "IT_HIGH",
                "reason": "IT High: Highest of three consecutive swing highs"
            }
        else:
            return {
                "is_it": False,
                "point_type": "ST_HIGH",
                "reason": "ST High: Not highest of three consecutive swing highs"
            }
    elif swing_type == "SWING_LOW":
        if left_swing_level > swing_level and right_swing_level > swing_level:
            return {
                "is_it": True,
                "point_type": "IT_LOW",
                "reason": "IT Low: Lowest of three consecutive swing lows"
            }
        else:
            return {
                "is_it": False,
                "point_type": "ST_LOW",
                "reason": "ST Low: Not lowest of three consecutive swing lows"
            }
    return {"is_it": False, "point_type": "UNKNOWN", "reason": "Invalid swing type"}

def scan_it_points(df):
    swings = scan_candles_for_swings(df)
    results = []
    
    # Separate highs and lows
    highs = [s for s in swings if s["swing_type"] == "SWING_HIGH"]
    lows = [s for s in swings if s["swing_type"] == "SWING_LOW"]
    
    # Process Highs
    for i in range(1, len(highs) - 1):
        left, mid, right = highs[i-1], highs[i], highs[i+1]
        res = classify_it_point(mid["swing_level"], "SWING_HIGH", left["swing_level"], right["swing_level"])
        if res["is_it"]:
            results.append({
                "datetime": mid["datetime"],
                "price_level": mid["swing_level"],
                "point_type": "IT_HIGH",
                "left_swing": left["swing_level"],
                "right_swing": right["swing_level"]
            })
            
    # Process Lows
    for i in range(1, len(lows) - 1):
        left, mid, right = lows[i-1], lows[i], lows[i+1]
        res = classify_it_point(mid["swing_level"], "SWING_LOW", left["swing_level"], right["swing_level"])
        if res["is_it"]:
            results.append({
                "datetime": mid["datetime"],
                "price_level": mid["swing_level"],
                "point_type": "IT_LOW",
                "left_swing": left["swing_level"],
                "right_swing": right["swing_level"]
            })
            
    # Sort results by datetime
    results.sort(key=lambda x: x["datetime"])
    return results

def determine_trend(it_points_list):
    it_highs = [p for p in it_points_list if p["point_type"] == "IT_HIGH"]
    it_lows = [p for p in it_points_list if p["point_type"] == "IT_LOW"]
    
    # Sort by datetime ascending
    it_highs.sort(key=lambda x: x["datetime"])
    it_lows.sort(key=lambda x: x["datetime"])
    
    last_h = it_highs[-1]["price_level"] if it_highs else None
    last_l = it_lows[-1]["price_level"] if it_lows else None
    
    if len(it_highs) < 2 or len(it_lows) < 2:
        return {"trend": "NEUTRAL", "reason": "Insufficient IT points for trend analysis", "last_it_high": last_h, "last_it_low": last_l}
    
    curr_h, prev_h = it_highs[-1]["price_level"], it_highs[-2]["price_level"]
    curr_l, prev_l = it_lows[-1]["price_level"], it_lows[-2]["price_level"]
    
    if curr_h > prev_h and curr_l > prev_l:
        return {"trend": "BULLISH", "reason": "Higher IT Highs and Higher IT Lows", "last_it_high": curr_h, "last_it_low": curr_l}
    elif curr_h < prev_h and curr_l < prev_l:
        return {"trend": "BEARISH", "reason": "Lower IT Highs and Lower IT Lows", "last_it_high": curr_h, "last_it_low": curr_l}
    else:
        return {"trend": "NEUTRAL", "reason": "Mixed signals: No clear HH/HL or LH/LL", "last_it_high": curr_h, "last_it_low": curr_l}

def is_it_protected(it_level, it_type, current_price):
    if it_type == "IT_HIGH":
        return current_price < it_level
    elif it_type == "IT_LOW":
        return current_price > it_level
    return False

def calculate_fva_boundaries(it_high, it_low):
    if it_high <= it_low:
        raise ValueError("IT High must be above IT Low")
    return {
        "fva_high": it_high,
        "fva_low": it_low,
        "fva_size": it_high - it_low
    }

def detect_overlapping_fvg(fva_high, fva_low, fvg_list):
    for fvg in fvg_list:
        if not fvg.get("is_mitigated", False):
            # BULLISH FVA overlaps with fva_low
            overlap_bull = fvg["fvg_high"] >= fva_low and fvg["fvg_low"] <= fva_low
            # BEARISH FVA overlaps with fva_high
            overlap_bear = fvg["fvg_low"] <= fva_high and fvg["fvg_high"] >= fva_high
            
            if overlap_bull or overlap_bear:
                quality = "HIGH" if fvg.get("fvg_type") == "PFVG" else "MEDIUM"
                return {"has_overlap": True, "overlapping_fvg": fvg, "overlap_quality": quality}
                
    return {"has_overlap": False, "overlapping_fvg": None, "overlap_quality": "NONE"}

def detect_nested_fva(fva_high, fva_low, it_points_list):
    # Sort points to find the innermost
    it_highs = sorted([p for p in it_points_list if p["point_type"] == "IT_HIGH" and fva_low < p["price_level"] < fva_high], key=lambda x: x["price_level"])
    it_lows = sorted([p for p in it_points_list if p["point_type"] == "IT_LOW" and fva_low < p["price_level"] < fva_high], key=lambda x: x["price_level"], reverse=True)
    
    if it_highs and it_lows:
        return {
            "has_nested": True,
            "nested_high": it_highs[0]["price_level"],
            "nested_low": it_lows[0]["price_level"]
        }
        
    return {"has_nested": False, "nested_high": None, "nested_low": None}

def classify_fva_type(has_overlapping_fvg, has_nested_fva, is_sweep):
    if has_overlapping_fvg and has_nested_fva and not is_sweep:
        return "IDEAL"
    elif has_overlapping_fvg and not is_sweep:
        return "GOOD"
    else:
        return "WEAK"

def detect_sweep_at_fva(fva_high, fva_low, candle_high, candle_low, candle_close, direction):
    if direction == "BULLISH":
        return candle_high > fva_high and candle_close < fva_high
    elif direction == "BEARISH":
        return candle_low < fva_low and candle_close > fva_low
    return False

def fair_value_theory_check(price, fva_high, fva_low, direction):
    if direction == "BULLISH":
        if fva_low <= price <= fva_high:
            return {"state": "OFFERING_FAIR_VALUE", "expected_action": "Continue higher from FVA", "reason": "Price is inside Bullish FVA"}
        elif price < fva_low:
            return {"state": "SEEKING_LIQUIDITY", "expected_action": "Target swing lows below (LOD)", "reason": "Price broke below Bullish FVA"}
        else:
            return {"state": "BEYOND_FVA", "expected_action": "Fast price action, minimal retracement", "reason": "Price has cleared Bullish FVA"}
    else: # BEARISH
        if fva_low <= price <= fva_high:
            return {"state": "OFFERING_FAIR_VALUE", "expected_action": "Continue lower from FVA", "reason": "Price is inside Bearish FVA"}
        elif price > fva_high:
            return {"state": "SEEKING_LIQUIDITY", "expected_action": "Target swing highs above (LOD)", "reason": "Price broke above Bearish FVA"}
        else:
            return {"state": "BEYOND_FVA", "expected_action": "Fast price action, minimal retracement", "reason": "Price has cleared Bearish FVA"}

def build_fva_from_it_points(it_high_price, it_low_price, instrument, fvg_list=None, it_points_list=None):
    if fvg_list is None: fvg_list = []
    if it_points_list is None: it_points_list = []
    
    bounds = calculate_fva_boundaries(it_high_price, it_low_price)
    fh, fl = bounds["fva_high"], bounds["fva_low"]
    
    overlap_res = detect_overlapping_fvg(fh, fl, fvg_list)
    nested_res = detect_nested_fva(fh, fl, it_points_list)
    
    is_sweep = False # Default unless candle data provided
    
    fva_type = classify_fva_type(overlap_res["has_overlap"], nested_res["has_nested"], is_sweep)
    size_pips = calculate_fvg_size_pips(fh, fl, instrument)
    
    prob = "LOW"
    if fva_type == "IDEAL": prob = "TRIPLE"
    elif fva_type == "GOOD": prob = "DOUBLE"
    
    return {
        "fva_high": fh,
        "fva_low": fl,
        "fva_size_pips": size_pips,
        "fva_type": fva_type,
        "has_overlapping_fvg": overlap_res["has_overlap"],
        "overlapping_fvg_id": overlap_res["overlapping_fvg"]["id"] if overlap_res["has_overlap"] and "id" in overlap_res["overlapping_fvg"] else None,
        "has_nested_fva": nested_res["has_nested"],
        "nested_fva_high": nested_res["nested_high"],
        "nested_fva_low": nested_res["nested_low"],
        "is_sweep": is_sweep,
        "probability": prob
    }

def full_market_structure_scan(instrument, timeframe):
    df = fetch_candles(instrument, timeframe)
    fvg_list = scan_candles_for_fvgs(df, instrument)
    swing_list = scan_candles_for_swings(df)
    it_points = scan_it_points(df)
    trend_state = determine_trend(it_points)
    
    # Simple FVA builder logic from most recent IT points
    fvas = []
    it_highs = [p for p in it_points if p["point_type"] == "IT_HIGH"]
    it_lows = [p for p in it_points if p["point_type"] == "IT_LOW"]
    
    if it_highs and it_lows:
        # Build one FVA from most recent high/low pair
        try:
            fva = build_fva_from_it_points(it_highs[-1]["price_level"], it_lows[-1]["price_level"], instrument, fvg_list, it_points)
            fvas.append(fva)
        except:
            pass # Skip if invalid boundaries
            
    return {
        "instrument": instrument,
        "timeframe": timeframe,
        "trend": trend_state["trend"],
        "last_it_high": trend_state["last_it_high"],
        "last_it_low": trend_state["last_it_low"],
        "trend_reason": trend_state["reason"],
        "it_points": it_points,
        "fair_value_areas": fvas,
        "total_it_highs": len(it_highs),
        "total_it_lows": len(it_lows),
        "total_fvas": len(fvas),
        "timeframe_strength": "STRONG" if timeframe in ["DAILY", "4H", "WEEKLY"] else "WEAK"
    }

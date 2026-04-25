import pandas as pd
import numpy as np
from modules.video1_pd_arrays import (
    scan_candles_for_fvgs,
    scan_candles_for_swings,
    classify_fvg_type,
    calculate_fvg_size_pips,
    check_mitigation,
    get_pip_multiplier,
    classify_pd_array
)
from modules.video2_market_structure import (
    scan_it_points,
    determine_trend,
    build_fva_from_it_points,
    fair_value_theory_check,
    classify_it_point
)
from modules.data_engine import fetch_candles

# --- CONSTANTS ---
FLOD_SCORES = {
    'FVG_IS_FLOD': 40,
    'FVA_IS_FLOD': 20
}

ODD_SCORES = {
    'FVA_IS_ODD': 35,
    'FVG_IS_ODD': 15,
    'NO_ODD': 0
}

FVG_TYPE_SCORES = {
    'PFVG': 25,
    'BFVG': 15,
    'RFVG': 0
}

FVA_TYPE_SCORES = {
    'IDEAL': 20,
    'GOOD': 12,
    'WEAK': 0,
    None: 5
}

LOD_SCORES = {
    'TRADE_FROM': 10,
    'TRADE_TOWARDS': 5
}

def validate_ofl_structure(swing_price, swing_type, fvg_dict, direction):
    if not fvg_dict:
        return {"is_valid": False, "reason": "No FVG present — this is not an Order Flow Lag"}
    
    if fvg_dict.get("is_mitigated"):
        return {"is_valid": False, "reason": "FVG is mitigated — OFL no longer valid"}
        
    if direction == "BULLISH":
        if swing_type != "SWING_LOW":
            return {"is_valid": False, "reason": "Bullish OFL requires SWING_LOW"}
        if fvg_dict["direction"] != "BULLISH":
            return {"is_valid": False, "reason": "Bullish OFL requires BULLISH FVG"}
    else: # BEARISH
        if swing_type != "SWING_HIGH":
            return {"is_valid": False, "reason": "Bearish OFL requires SWING_HIGH"}
        if fvg_dict["direction"] != "BEARISH":
            return {"is_valid": False, "reason": "Bearish OFL requires BEARISH FVG"}
            
    return {"is_valid": True, "reason": "Valid OFL structure"}

def identify_flod(fvg_high, fvg_low, fva_high, fva_low, direction):
    # If no FVA, FVG is FLOD by default
    if fva_high is None or fva_low is None:
        return {"flod_type": "FVG_IS_FLOD", "flod_high": fvg_high, "flod_low": fvg_low, "quality": "HIGH", "score": FLOD_SCORES['FVG_IS_FLOD']}

    if direction == "BULLISH":
        # First pda hit from above = the one with HIGHER low
        if fvg_low > fva_low:
            return {"flod_type": "FVG_IS_FLOD", "flod_high": fvg_high, "flod_low": fvg_low, "quality": "HIGH", "score": FLOD_SCORES['FVG_IS_FLOD']}
        else:
            return {"flod_type": "FVA_IS_FLOD", "flod_high": fva_high, "flod_low": fva_low, "quality": "LOW", "score": FLOD_SCORES['FVA_IS_FLOD']}
    else: # BEARISH
        # First pda hit from below = the one with LOWER high
        if fvg_high < fva_high:
            return {"flod_type": "FVG_IS_FLOD", "flod_high": fvg_high, "flod_low": fvg_low, "quality": "HIGH", "score": FLOD_SCORES['FVG_IS_FLOD']}
        else:
            return {"flod_type": "FVA_IS_FLOD", "flod_high": fva_high, "flod_low": fva_low, "quality": "LOW", "score": FLOD_SCORES['FVA_IS_FLOD']}

def identify_odd(fvg_high, fvg_low, fva_high, fva_low, flod_type, direction):
    if fva_high is None or fva_low is None:
        return {"odd_type": "NO_ODD", "odd_high": None, "odd_low": None, "overlap_size": 0, "quality": "NONE", "score": 0}

    overlap_high = min(fvg_high, fva_high)
    overlap_low = max(fvg_low, fva_low)
    overlap_size = overlap_high - overlap_low
    
    if overlap_size <= 0:
        return {"odd_type": "NO_ODD", "odd_high": None, "odd_low": None, "overlap_size": 0, "quality": "NONE", "score": 0}
        
    if flod_type == "FVG_IS_FLOD":
        # FVA is the ODD
        return {"odd_type": "FVA_IS_ODD", "odd_high": overlap_high, "odd_low": overlap_low, "overlap_size": overlap_size, "quality": "HIGH", "score": ODD_SCORES['FVA_IS_ODD']}
    else:
        # FVG is the ODD
        return {"odd_type": "FVG_IS_ODD", "odd_high": overlap_high, "odd_low": overlap_low, "overlap_size": overlap_size, "quality": "LOW", "score": ODD_SCORES['FVG_IS_ODD']}

def identify_lod(swing_price, has_fvg_in_lag):
    if has_fvg_in_lag:
        return {
            "lod_price": swing_price,
            "lod_action": "TRADE_TOWARDS",
            "lod_score": LOD_SCORES["TRADE_TOWARDS"],
            "explanation": "LOD is a target — if FVA and FVG fail, price seeks liquidity at swing point"
        }
    else:
        return {
            "lod_price": swing_price,
            "lod_action": "TRADE_FROM",
            "lod_score": LOD_SCORES["TRADE_FROM"],
            "explanation": "LOD is entry — sweep this swing point then continue in trend direction"
        }

def calculate_ofl_probability(flod_score, odd_score, fvg_type_score, fva_type_score, lod_score):
    total_score = flod_score + odd_score + fvg_type_score + fva_type_score + lod_score
    max_possible = 130
    normalized = (total_score / max_possible) * 100
    
    label = "LOW"
    if normalized >= 75: label = "HIGH"
    elif normalized >= 45: label = "MEDIUM"
    
    return {
        "total_score": round(normalized, 2),
        "probability_label": label,
        "breakdown": {
            "flod_score": flod_score,
            "odd_score": odd_score,
            "fvg_type_score": fvg_type_score,
            "fva_type_score": fva_type_score,
            "lod_score": lod_score,
            "raw_total": total_score,
            "max_possible": max_possible
        }
    }

def generate_ofl_trading_notes(flod_type, odd_type, lod_action, probability_label, fvg_type):
    notes = []
    if probability_label == "HIGH":
        notes.append("HIGH PROBABILITY OFL — prioritize this setup")
    elif probability_label == "LOW":
        notes.append("LOW PROBABILITY — avoid or wait for confirmation")
        
    if flod_type == "FVG_IS_FLOD":
        notes.append("Strong intention — FVG is FLOD, minimal retracement")
    else:
        notes.append("Deep retracement — FVA is FLOD, weaker setup")
        
    if odd_type == "FVA_IS_ODD":
        notes.append("Double probability zone — FVA overlaps FVG at ODD")
        
    if fvg_type == "RFVG":
        notes.append("WARNING: Rejection FVG — require extra confirmation")
    elif fvg_type == "PFVG":
        notes.append("Perfect FVG — ideal entry zone")
        
    if lod_action == "TRADE_FROM":
        notes.append("LOD: sweep swing point then enter")
    else:
        notes.append("LOD: if FVA fails, price seeks liquidity here")
        
    return "\n".join(notes)

def build_ofl(swing_price, swing_type, fvg_dict, fva_dict, direction, instrument):
    val = validate_ofl_structure(swing_price, swing_type, fvg_dict, direction)
    if not val["is_valid"]:
        raise ValueError(val["reason"])
        
    fvh, fvl = fvg_dict["fvg_high"], fvg_dict["fvg_low"]
    fah, fal = fva_dict.get("fva_high"), fva_dict.get("fva_low")
    fat = fva_dict.get("fva_type")
    
    flod = identify_flod(fvh, fvl, fah, fal, direction)
    odd = identify_odd(fvh, fvl, fah, fal, flod["flod_type"], direction)
    lod = identify_lod(swing_price, has_fvg_in_lag=True)
    
    fvg_score = FVG_TYPE_SCORES.get(fvg_dict["fvg_type"], 0)
    fva_score = FVA_TYPE_SCORES.get(fat) if fat else FVA_TYPE_SCORES[None]
    
    prob = calculate_ofl_probability(flod["score"], odd["score"], fvg_score, fva_score, lod["lod_score"])
    
    # Hard rule: RFVG = Low Probability
    if fvg_dict["fvg_type"] == "RFVG":
        prob["probability_label"] = "LOW"
        
    notes = generate_ofl_trading_notes(flod["flod_type"], odd["odd_type"], lod["lod_action"], prob["probability_label"], fvg_dict["fvg_type"])
    
    return {
        "direction": direction,
        "swing_point_price": swing_price,
        "swing_point_type": swing_type,
        "fvg_high": fvh,
        "fvg_low": fvl,
        "fvg_type": fvg_dict["fvg_type"],
        "fva_high": fah,
        "fva_low": fal,
        "fva_type": fat,
        "flod": flod,
        "odd": odd,
        "lod": lod,
        "probability_score": prob["total_score"],
        "probability_label": prob["probability_label"],
        "probability_breakdown": prob["breakdown"],
        "invalidation_price": swing_price,
        "is_confirmed": True,
        "trading_notes": notes
    }

def check_ofl_invalidation(ofl_dict, current_price):
    if ofl_dict["direction"] == "BULLISH":
        if current_price < ofl_dict["swing_point_price"]:
            return {"is_invalidated": True, "reason": "Price closed below swing low"}
    else: # BEARISH
        if current_price > ofl_dict["swing_point_price"]:
            return {"is_invalidated": True, "reason": "Price closed above swing high"}
    return {"is_invalidated": False, "reason": "Price within bounds"}

def scan_candles_for_ofls(df, instrument):
    fvgs = scan_candles_for_fvgs(df, instrument)
    swings = scan_candles_for_swings(df)
    
    # Sort FVGs by datetime for pointer efficiency
    fvgs_sorted = sorted(fvgs, key=lambda x: x["candle1_datetime"])
    
    results = []
    fvg_ptr = 0
    
    for s in swings:
        # Move fvg_ptr to the first FVG that starts at or after this swing
        while fvg_ptr < len(fvgs_sorted) and fvgs_sorted[fvg_ptr]["candle1_datetime"] < s["datetime"]:
            fvg_ptr += 1
            
        # Check subsequent FVGs for a match
        # Usually the OFL FVG is within the next few candles
        match_ptr = fvg_ptr
        target_dir = ("BULLISH" if s["swing_type"] == "SWING_LOW" else "BEARISH")
        
        while match_ptr < len(fvgs_sorted) and match_ptr < fvg_ptr + 10: # Lookahead 10 FVGs max
            fvg = fvgs_sorted[match_ptr]
            if fvg["direction"] == target_dir:
                try:
                    ofl = build_ofl(s["swing_level"], s["swing_type"], fvg, {}, target_dir, instrument)
                    ofl["datetime"] = s["datetime"]
                    results.append(ofl)
                    break # Found the closest matching FVG
                except:
                    pass
            match_ptr += 1
            
    results.sort(key=lambda x: x["datetime"], reverse=True)
    return results

def get_ofl_intention(ofl_dict):
    if ofl_dict["direction"] == "BULLISH":
        if ofl_dict["probability_label"] == "HIGH":
            return {"intention": "CONTINUE_HIGHER", "explanation": "Price intends to continue higher — swing low + FVG shows bullish strength"}
        elif ofl_dict["probability_label"] == "MEDIUM":
            return {"intention": "PROBABLE_UP", "explanation": "Moderate confidence in up direction"}
    else:
        if ofl_dict["probability_label"] == "HIGH":
            return {"intention": "CONTINUE_LOWER", "explanation": "Price intends to continue lower — swing high + FVG shows bearish strength"}
        elif ofl_dict["probability_label"] == "MEDIUM":
            return {"intention": "PROBABLE_DOWN", "explanation": "Moderate confidence in down direction"}
            
    return {"intention": "UNCERTAIN", "explanation": "Low confidence — wait for more confirmation"}

def compare_ofl_timeframes(instrument, timeframes_list):
    analyses = {}
    total_score = 0
    count = 0
    directions = []
    
    for tf in timeframes_list:
        df = fetch_candles(instrument, tf)
        ofls = scan_candles_for_ofls(df, instrument)
        analyses[tf] = ofls
        if ofls:
            total_score += sum(o["probability_score"] for o in ofls) / len(ofls)
            count += 1
            directions.append(ofls[0]["direction"])
            
    avg_score = total_score / count if count > 0 else 0
    alignment = "ALIGNED" if len(set(directions)) == 1 and count > 0 else "MIXED"
    
    return {
        "timeframe_analyses": analyses,
        "average_probability": avg_score,
        "alignment": alignment,
        "recommendation": "STRONG CONFLUENCE" if alignment == "ALIGNED" and avg_score > 70 else "Wait for alignment"
    }

from functools import lru_cache
from modules.data_engine import fetch_candles, BACKTEST_MODE, BACKTEST_END_DATE

@lru_cache(maxsize=1024)
def _cached_full_order_flow_scan(instrument, timeframe, context_date):
    df = fetch_candles(instrument, timeframe)
    ofls = scan_candles_for_ofls(df, instrument)
    
    bullish = [o for o in ofls if o["direction"] == "BULLISH"]
    bearish = [o for o in ofls if o["direction"] == "BEARISH"]
    
    intention = get_ofl_intention(ofls[0]) if ofls else {"intention": "NONE", "explanation": "No OFLs found"}
    
    return {
        "instrument": instrument,
        "timeframe": timeframe,
        "total_ofls": len(ofls),
        "bullish_ofls": len(bullish),
        "bearish_ofls": len(bearish),
        "high_prob_ofls": len([o for o in ofls if o["probability_label"] == "HIGH"]),
        "medium_prob_ofls": len([o for o in ofls if o["probability_label"] == "MEDIUM"]),
        "low_prob_ofls": len([o for o in ofls if o["probability_label"] == "LOW"]),
        "most_recent_ofl": ofls[0] if ofls else None,
        "current_intention": intention,
        "all_ofls": ofls
    }

def full_order_flow_scan(instrument: str, timeframe: str, context_date: str = None) :
    """
    Scans for Order Flow Levels. In backtest mode, it uses the global context for caching.
    """
    if context_date is None and BACKTEST_MODE:
        context_date = BACKTEST_END_DATE
    
    # If still None (live mode), we use a placeholder for the cache to prevent redundant live scans per candle
    if context_date is None:
        context_date = "LIVE"
        
    return _cached_full_order_flow_scan(instrument, timeframe, context_date)

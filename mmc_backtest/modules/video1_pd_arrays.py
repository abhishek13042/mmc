import pandas as pd
import numpy as np
try:
    from modules.data_engine import fetch_candles, SUPPORTED_INSTRUMENTS as VALID_INSTRUMENTS, VALID_TIMEFRAMES
except ImportError:
    # Fallback for when running from root vs. package context
    from modules.data_engine import fetch_candles, SUPPORTED_INSTRUMENTS as VALID_INSTRUMENTS, VALID_TIMEFRAMES

# --- CONSTANTS ---
PIP_MULTIPLIER = {
    "EURUSD": 10000,
    "GBPUSD": 10000,
    "XAUUSD": 10
}

FVG_TYPE_PRIORITY = {
    "PFVG": 1,  # Best — trade this
    "BFVG": 2,  # Medium — go lower TF
    "RFVG": 3   # Worst — avoid
}

PD_ARRAY_HIERARCHY = [
    {"rank": 1, "type": "FVG",
     "note": "King — no OFL without FVG, no FVA without FVG"},
    {"rank": 2, "type": "FAIR_VALUE_AREA",
     "note": "Trade FROM it mainly — needs FVG to exist"},
    {"rank": 3, "type": "SWING_POINT",
     "note": "Liquidity — big entities target these"}
]

def get_pip_multiplier(instrument):
    if instrument not in PIP_MULTIPLIER:
        raise ValueError(f"Invalid instrument for pip calculation: {instrument}")
    return PIP_MULTIPLIER[instrument]

def calculate_fvg_size_pips(fvg_high, fvg_low, instrument):
    size = (fvg_high - fvg_low) * get_pip_multiplier(instrument)
    return round(float(size), 2)

def validate_bullish_fvg(c1_high, c1_low, c2_high, c2_low, c3_high, c3_low, c2_close=None):
    # Expansion check: c2_close must be above c1_high
    # Note: If c2_close is not provided, we use a slightly more relaxed check or assume expansion happened if c2_high is high enough
    if c2_close is not None and c2_close <= c1_high:
        return {"is_valid": False, "reason": "No expansion: Candle 2 close not above Candle 1 high"}
    
    # Gap check: c3_low must be GREATER THAN c1_high
    if c3_low <= c1_high:
        return {"is_valid": False, "reason": "No gap: Candle 3 low not above Candle 1 high"}
    
    fvg_high = c1_high
    fvg_low = c3_low
    gap_size = fvg_low - fvg_high # Wait, for Bullish FVG, c3_low is the floor, and c1_high is the roof. 
    # Actually MMC logic: FVG is between c1_high and c3_low. 
    # If c3_low > c1_high, it's a gap.
    # fvg_high = c3_low, fvg_low = c1_high
    fvg_high = c3_low
    fvg_low = c1_high
    gap_size = fvg_high - fvg_low
    
    if gap_size <= 0:
        return {"is_valid": False, "reason": "Gap size is zero or negative"}
        
    return {
        "is_valid": True,
        "fvg_high": fvg_high,
        "fvg_low": fvg_low,
        "reason": "Valid bullish FVG"
    }

def validate_bearish_fvg(c1_high, c1_low, c2_high, c2_low, c3_high, c3_low, c2_close=None):
    # Expansion check: c2_low must be below c1_low
    if c2_close is not None and c2_close >= c1_low:
        return {"is_valid": False, "reason": "No expansion: Candle 2 close not below Candle 1 low"}
    
    # Gap check: c3_high must be LESS THAN c1_low
    if c3_high >= c1_low:
        return {"is_valid": False, "reason": "No gap: Candle 3 high not below Candle 1 low"}
    
    # fvg_high = c1_low, fvg_low = c3_high
    fvg_high = c1_low
    fvg_low = c3_high
    gap_size = fvg_high - fvg_low
    
    if gap_size <= 0:
        return {"is_valid": False, "reason": "Gap size is zero or negative"}
        
    return {
        "is_valid": True,
        "fvg_high": fvg_high,
        "fvg_low": fvg_low,
        "reason": "Valid bearish FVG"
    }

def calculate_rejection_ratio(fvg_high, fvg_low, c3_high, c3_low, direction):
    potential_gap = fvg_high - fvg_low
    if potential_gap <= 0:
        return 0.0
        
    if direction == "BULLISH":
        # fvg_high=c3_low, fvg_low=c1_high
        # candle3_intrusion: how much of the gap was filled by c3's body/wick?
        # Actually, the instructions say: 
        # BULLISH: candle3_intrusion = max(0, c3_high - fvg_low) 
        # Wait, if c3_low > c1_high, then fvg_low=c1_high. 
        # If candle 3 rejected, it means it went into the gap then came back? 
        # Instructions: "how much of the gap was rejected by candle3"
        # PFVG = consolidation 3rd candle. 
        # RFVG = rejection 3rd candle.
        candle3_intrusion = max(0, c3_high - fvg_high) # This logic seems specific to MMC
        # Let's follow the prompt exactly:
        # BULLISH: candle3_intrusion = max(0, c3_high - fvg_low)
        # BEARISH: candle3_intrusion = max(0, fvg_high - c3_low)
        candle3_intrusion = max(0, c3_high - fvg_low)
        rejection_ratio = candle3_intrusion / potential_gap
    else: # BEARISH
        candle3_intrusion = max(0, fvg_high - c3_low)
        rejection_ratio = candle3_intrusion / potential_gap
        
    return round(float(min(rejection_ratio, 1.0)), 4)

def classify_fvg_type(rejection_ratio, c3_high, c3_low, c2_high, c2_low, direction):
    if rejection_ratio < 0.25:
        return "PFVG"
    
    if rejection_ratio >= 0.25:
        if direction == "BULLISH":
            if c3_high > c2_high:
                return "BFVG"
        else: # BEARISH
            if c3_low < c2_low:
                return "BFVG"
    
    return "RFVG"

def validate_swing_high(left_high, middle_high, right_high):
    is_valid = middle_high > left_high and middle_high > right_high
    return {
        "is_valid": is_valid,
        "swing_level": middle_high if is_valid else None,
        "reason": "Valid swing high" if is_valid else "Not a swing high: middle candle not highest"
    }

def validate_swing_low(left_low, middle_low, right_low):
    is_valid = middle_low < left_low and middle_low < right_low
    return {
        "is_valid": is_valid,
        "swing_level": middle_low if is_valid else None,
        "reason": "Valid swing low" if is_valid else "Not a swing low: middle candle not lowest"
    }

def classify_swing_structure(swing_level, swing_type, left_swing, right_swing):
    if swing_type == "SWING_HIGH":
        if left_swing is not None and right_swing is not None:
            if left_swing < swing_level and right_swing < swing_level:
                return "IT"
    elif swing_type == "SWING_LOW":
        if left_swing is not None and right_swing is not None:
            if left_swing > swing_level and right_swing > swing_level:
                return "IT"
    return "ST"

def classify_liquidity_event(swing_level, swing_type, next_candle_high, next_candle_low, next_candle_close):
    if swing_type == "SWING_HIGH":
        if next_candle_high > swing_level and next_candle_close < swing_level:
            return "SWEEP"
        if next_candle_close > swing_level:
            return "RUN"
    elif swing_type == "SWING_LOW":
        if next_candle_low < swing_level and next_candle_close > swing_level:
            return "SWEEP"
        if next_candle_close < swing_level:
            return "RUN"
    return "UNKNOWN"

def classify_pd_array(array_type, direction):
    if array_type == "FVG":
        if direction == "BULLISH": return "DISCOUNT"
        if direction == "BEARISH": return "PREMIUM"
    elif array_type == "SWING_POINT":
        if direction == "SWING_LOW": return "DISCOUNT"
        if direction == "SWING_HIGH": return "PREMIUM"
    elif array_type == "FAIR_VALUE_AREA":
        if direction == "BULLISH": return "DISCOUNT"
        if direction == "BEARISH": return "PREMIUM"
    return "UNKNOWN"

def check_mitigation(fvg_high, fvg_low, price, direction):
    if fvg_low <= price <= fvg_high:
        return True
    return False

def scan_candles_for_fvgs(df, instrument):
    required_cols = ['open', 'high', 'low', 'close', 'datetime']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"DataFrame missing column: {col}")
    
    # Use numpy arrays for speed
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    dts = df['datetime'].values
    
    results = []
    for i in range(len(df) - 2):
        # Bullish
        bull_res = validate_bullish_fvg(highs[i], lows[i], highs[i+1], lows[i+1], highs[i+2], lows[i+2], closes[i+1])
        if bull_res["is_valid"]:
            rr = calculate_rejection_ratio(bull_res["fvg_high"], bull_res["fvg_low"], highs[i+2], lows[i+2], "BULLISH")
            ft = classify_fvg_type(rr, highs[i+2], lows[i+2], highs[i+1], lows[i+1], "BULLISH")
            fs = calculate_fvg_size_pips(bull_res["fvg_high"], bull_res["fvg_low"], instrument)
            results.append({
                "direction": "BULLISH",
                "fvg_high": bull_res["fvg_high"], "fvg_low": bull_res["fvg_low"],
                "fvg_type": ft, "fvg_size_pips": fs, "rejection_ratio": rr,
                "candle1_datetime": dts[i], "candle3_datetime": dts[i+2],
                "candle1_high": highs[i], "candle1_low": lows[i],
                "candle2_high": highs[i+1], "candle2_low": lows[i+1],
                "candle3_high": highs[i+2], "candle3_low": lows[i+2],
                "is_mitigated": False
            })
            
        # Bearish
        bear_res = validate_bearish_fvg(highs[i], lows[i], highs[i+1], lows[i+1], highs[i+2], lows[i+2], closes[i+1])
        if bear_res["is_valid"]:
            rr = calculate_rejection_ratio(bear_res["fvg_high"], bear_res["fvg_low"], highs[i+2], lows[i+2], "BEARISH")
            ft = classify_fvg_type(rr, highs[i+2], lows[i+2], highs[i+1], lows[i+1], "BEARISH")
            fs = calculate_fvg_size_pips(bear_res["fvg_high"], bear_res["fvg_low"], instrument)
            results.append({
                "direction": "BEARISH",
                "fvg_high": bear_res["fvg_high"], "fvg_low": bear_res["fvg_low"],
                "fvg_type": ft, "fvg_size_pips": fs, "rejection_ratio": rr,
                "candle1_datetime": dts[i], "candle3_datetime": dts[i+2],
                "candle1_high": highs[i], "candle1_low": lows[i],
                "candle2_high": highs[i+1], "candle2_low": lows[i+1],
                "candle3_high": highs[i+2], "candle3_low": lows[i+2],
                "is_mitigated": False
            })
            
    return results

def scan_candles_for_swings(df):
    highs = df['high'].values
    lows = df['low'].values
    dts = df['datetime'].values
    
    results = []
    for i in range(1, len(df) - 1):
        # High
        if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
            results.append({
                "swing_type": "SWING_HIGH", "swing_level": highs[i],
                "datetime": dts[i], "is_confirmed": True, "is_mitigated": False
            })
            
        # Low
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
            results.append({
                "swing_type": "SWING_LOW", "swing_level": lows[i],
                "datetime": dts[i], "is_confirmed": True, "is_mitigated": False
            })
    return results

def get_unmitigated_fvgs(fvg_list, current_price):
    unmitigated = []
    for fvg in fvg_list:
        if not fvg["is_mitigated"]:
            if check_mitigation(fvg["fvg_high"], fvg["fvg_low"], current_price, fvg["direction"]):
                fvg["is_mitigated"] = True
            else:
                unmitigated.append(fvg)
    
    # Sort by proximity to current_price
    unmitigated.sort(key=lambda x: min(abs(x["fvg_high"] - current_price), abs(x["fvg_low"] - current_price)))
    return unmitigated

def full_pd_array_scan(instrument, timeframe):
    df = fetch_candles(instrument, timeframe)
    fvgs = scan_candles_for_fvgs(df, instrument)
    swings = scan_candles_for_swings(df)
    
    stats = {
        "instrument": instrument,
        "timeframe": timeframe,
        "total_fvgs": len(fvgs),
        "total_swings": len(swings),
        "bullish_fvgs": len([f for f in fvgs if f["direction"] == "BULLISH"]),
        "bearish_fvgs": len([f for f in fvgs if f["direction"] == "BEARISH"]),
        "pfvg_count": len([f for f in fvgs if f["fvg_type"] == "PFVG"]),
        "bfvg_count": len([f for f in fvgs if f["fvg_type"] == "BFVG"]),
        "rfvg_count": len([f for f in fvgs if f["fvg_type"] == "RFVG"]),
        "fvgs": fvgs,
        "swings": swings,
        "pd_array_hierarchy": PD_ARRAY_HIERARCHY
    }
    return stats

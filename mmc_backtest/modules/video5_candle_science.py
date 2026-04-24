import pandas as pd
import numpy as np
from modules.data_engine import (
    fetch_candles, SUPPORTED_INSTRUMENTS, VALID_TIMEFRAMES
)
# For backward compatibility
VALID_INSTRUMENTS = SUPPORTED_INSTRUMENTS

from modules.video1_pd_arrays import (
    scan_candles_for_fvgs,
    scan_candles_for_swings
)
from modules.video3_4_order_flow import (
    scan_candles_for_ofls,
    full_order_flow_scan
)

# --- CONSTANTS ---
CANDLE_SCIENCE_TF_PAIRS = {
    'MONTHLY': 'DAILY',
    'WEEKLY':  'DAILY',
    'DAILY':   '4H',
    '4H':      '1H',
    '1H':      '15M',
    '15M':     '5M',
    '5M':      '1M'
}

DISRESPECT_BODY_THRESHOLD   = 0.55
RESPECT_WICK_THRESHOLD      = 0.30

CONFIDENCE_WEIGHTS = {
    'body_ratio':       30,
    'wick_ratio':       30,
    'ofl_alignment':    40
}

def calculate_candle_metrics(open_p, high_p, low_p, close_p):
    body_size      = abs(close_p - open_p)
    upper_wick     = high_p - max(open_p, close_p)
    lower_wick     = min(open_p, close_p) - low_p
    total_range    = high_p - low_p
    
    if total_range == 0:
        return {
            'body_size': 0.0, 'upper_wick': 0.0, 'lower_wick': 0.0,
            'total_range': 0.0, 'body_ratio': 0.0,
            'upper_wick_ratio': 0.0, 'lower_wick_ratio': 0.0,
            'candle_direction': 'NEUTRAL'
        }
        
    body_ratio       = round(body_size / total_range, 4)
    upper_wick_ratio = round(upper_wick / total_range, 4)
    lower_wick_ratio = round(lower_wick / total_range, 4)
    candle_direction = 'UP' if close_p >= open_p else 'DOWN'
    
    return {
        'body_size': body_size,
        'upper_wick': upper_wick,
        'lower_wick': lower_wick,
        'total_range': total_range,
        'body_ratio': body_ratio,
        'upper_wick_ratio': upper_wick_ratio,
        'lower_wick_ratio': lower_wick_ratio,
        'candle_direction': candle_direction
    }

def classify_disrespect_candle(metrics):
    if metrics['candle_direction'] == 'UP' and metrics['body_ratio'] >= DISRESPECT_BODY_THRESHOLD and metrics['upper_wick_ratio'] < RESPECT_WICK_THRESHOLD:
        return {'is_disrespect': True, 'direction': 'BULLISH', 'reason': 'Strong up candle, minimal top wick'}
    if metrics['candle_direction'] == 'DOWN' and metrics['body_ratio'] >= DISRESPECT_BODY_THRESHOLD and metrics['lower_wick_ratio'] < RESPECT_WICK_THRESHOLD:
        return {'is_disrespect': True, 'direction': 'BEARISH', 'reason': 'Strong down candle, minimal bottom wick'}
    return {'is_disrespect': False, 'direction': None, 'reason': None}

def classify_respect_candle(metrics):
    if metrics['lower_wick_ratio'] >= RESPECT_WICK_THRESHOLD:
        return {'is_respect': True, 'direction': 'BULLISH', 'reason': 'Long lower wick, swept lows'}
    if metrics['upper_wick_ratio'] >= RESPECT_WICK_THRESHOLD:
        return {'is_respect': True, 'direction': 'BEARISH', 'reason': 'Long upper wick, swept highs'}
    return {'is_respect': False, 'direction': None, 'reason': None}

def classify_candle_type(metrics):
    respect = classify_respect_candle(metrics)
    disrespect = classify_disrespect_candle(metrics)
    
    # Priority: Respect > Disrespect
    if respect['is_respect']:
        return {
            'candle_type': f"RESPECT_{respect['direction']}",
            'expected_next': 'CONTINUE_HIGHER' if respect['direction'] == 'BULLISH' else 'CONTINUE_LOWER',
            'confidence_base': (metrics['lower_wick_ratio'] if respect['direction'] == 'BULLISH' else metrics['upper_wick_ratio']) * 100
        }
    if disrespect['is_disrespect']:
        return {
            'candle_type': f"DISRESPECT_{disrespect['direction']}",
            'expected_next': 'CONTINUE_HIGHER' if disrespect['direction'] == 'BULLISH' else 'CONTINUE_LOWER',
            'confidence_base': metrics['body_ratio'] * 100
        }
    return {'candle_type': 'NEUTRAL', 'expected_next': 'NEUTRAL', 'confidence_base': 0.0}

def calculate_candle_confidence(candle_type, metrics, ofl_alignment):
    body_score = metrics['body_ratio'] * CONFIDENCE_WEIGHTS['body_ratio']
    
    if "DISRESPECT" in candle_type:
        wick_ratio = metrics['upper_wick_ratio'] if "BULLISH" in candle_type else metrics['lower_wick_ratio']
        wick_score = (1 - wick_ratio) * CONFIDENCE_WEIGHTS['wick_ratio']
    elif "RESPECT" in candle_type:
        wick_ratio = metrics['lower_wick_ratio'] if "BULLISH" in candle_type else metrics['upper_wick_ratio']
        wick_score = wick_ratio * CONFIDENCE_WEIGHTS['wick_ratio']
    else:
        return 0.0
        
    ofl_score_map = {'BULLISH_OFL': 1.0, 'BEARISH_OFL': 1.0, 'MIXED': 0.5, 'UNKNOWN': 0.25}
    # Check alignment
    is_aligned = ("BULLISH" in candle_type and ofl_alignment == "BULLISH_OFL") or \
                 ("BEARISH" in candle_type and ofl_alignment == "BEARISH_OFL")
    
    ofl_mult = 1.0 if is_aligned else (0.5 if ofl_alignment == "MIXED" else 0.25)
    ofl_score = CONFIDENCE_WEIGHTS['ofl_alignment'] * ofl_mult
    
    total = body_score + wick_score + ofl_score
    return round(min(total, 100.0), 2)

def get_lower_tf_ofl_alignment(instrument, candle_tf, candle_open_dt, candle_close_dt):
    lower_tf = CANDLE_SCIENCE_TF_PAIRS.get(candle_tf)
    if not lower_tf:
        return "UNKNOWN"
        
    df = fetch_candles(instrument, lower_tf)
    # Filter by datetime
    mask = (df['datetime'] >= candle_open_dt) & (df['datetime'] < candle_close_dt)
    df_subset = df.loc[mask]
    
    if df_subset.empty:
        return "UNKNOWN"
        
    ofls = scan_candles_for_ofls(df_subset, instrument)
    bull_count = len([o for o in ofls if o['direction'] == 'BULLISH'])
    bear_count = len([o for o in ofls if o['direction'] == 'BEARISH'])
    
    if bull_count > 0 and bear_count == 0: return "BULLISH_OFL"
    if bear_count > 0 and bull_count == 0: return "BEARISH_OFL"
    if bull_count > 0 and bear_count > 0: return "MIXED"
    return "UNKNOWN"

def analyze_single_candle(instrument, timeframe, candle_row):
    metrics = calculate_candle_metrics(
        candle_row['open'], candle_row['high'], candle_row['low'], candle_row['close']
    )
    classification = classify_candle_type(metrics)
    
    # Try to get candle close datetime for lower TF filtering
    # Since we usually only have start datetime, we approximate close as next candle start
    # but for a single row provided we might just use its own datetime and let the filter handle it
    ofl_alignment = get_lower_tf_ofl_alignment(instrument, timeframe, candle_row['datetime'], candle_row['datetime'])
    
    confidence = calculate_candle_confidence(classification['candle_type'], metrics, ofl_alignment)
    
    return {
        'instrument': instrument,
        'timeframe': timeframe,
        'candle_datetime': candle_row['datetime'],
        'open_price': candle_row['open'],
        'high_price': candle_row['high'],
        'low_price': candle_row['low'],
        'close_price': candle_row['close'],
        'candle_type': classification['candle_type'],
        'candle_direction': metrics['candle_direction'],
        'body_size': metrics['body_size'],
        'upper_wick': metrics['upper_wick'],
        'lower_wick': metrics['lower_wick'],
        'total_range': metrics['total_range'],
        'body_ratio': metrics['body_ratio'],
        'upper_wick_ratio': metrics['upper_wick_ratio'],
        'lower_wick_ratio': metrics['lower_wick_ratio'],
        'expected_next': classification['expected_next'],
        'lower_tf_inside': ofl_alignment,
        'confidence_score': confidence,
        'trade_date': str(candle_row['datetime']).split(' ')[0]
    }

def scan_candles_science(instrument, timeframe):
    df = fetch_candles(instrument, timeframe)
    results = []
    # Drop most recent forming candle
    df_closed = df.iloc[:-1]
    
    for _, row in df_closed.iterrows():
        analysis = analyze_single_candle(instrument, timeframe, row)
        if analysis['candle_type'] != 'NEUTRAL':
            results.append(analysis)
            
    results.sort(key=lambda x: x['candle_datetime'], reverse=True)
    return results

from functools import lru_cache
from modules.data_engine import fetch_candles, BACKTEST_MODE, BACKTEST_END_DATE

@lru_cache(maxsize=512)
def _cached_get_candle_science_bias(instrument, context_date):
    tfs = ['MONTHLY', 'WEEKLY', 'DAILY']
    bias_data = {'instrument': instrument}
    
    directions = []
    
    for tf in tfs:
        try:
            df = fetch_candles(instrument, tf)
            # Most recent closed candle
            last_row = df.iloc[-2] if len(df) > 1 else df.iloc[-1]
            analysis = analyze_single_candle(instrument, tf, last_row)
            
            prefix = tf.lower()
            bias_data[f'{prefix}_bias'] = 'BULLISH' if analysis['expected_next'] == 'CONTINUE_HIGHER' else \
                                          ('BEARISH' if analysis['expected_next'] == 'CONTINUE_LOWER' else 'NEUTRAL')
            bias_data[f'{prefix}_candle_type'] = analysis['candle_type']
            bias_data[f'{prefix}_confidence'] = analysis['confidence_score']
            
            if bias_data[f'{prefix}_bias'] != 'NEUTRAL':
                directions.append(bias_data[f'{prefix}_bias'])
        except Exception:
            # Skip if TF data is not available
            prefix = tf.lower()
            bias_data[f'{prefix}_bias'] = 'NEUTRAL'
            bias_data[f'{prefix}_confidence'] = 0.0
            continue
            
    # Overall bias logic
    if directions.count('BULLISH') == 3:
        bias_data['overall_bias'] = 'BULLISH'
        bias_data['bias_confidence'] = 'HIGH'
    elif directions.count('BEARISH') == 3:
        bias_data['overall_bias'] = 'BEARISH'
        bias_data['bias_confidence'] = 'HIGH'
    elif directions.count('BULLISH') >= 2:
        bias_data['overall_bias'] = 'BULLISH'
        bias_data['bias_confidence'] = 'MEDIUM'
    elif directions.count('BEARISH') >= 2:
        bias_data['overall_bias'] = 'BEARISH'
        bias_data['bias_confidence'] = 'MEDIUM'
    else:
        bias_data['overall_bias'] = 'NEUTRAL'
        bias_data['bias_confidence'] = 'LOW'
        
    return bias_data

def get_candle_science_bias(instrument: str, context_date: str = None) :
    """
    Determines HTF bias using candle science. In backtest mode, it uses the global context for caching.
    """
    if context_date is None and BACKTEST_MODE:
        context_date = BACKTEST_END_DATE
    
    if context_date is None:
        context_date = "LIVE"
        
    return _cached_get_candle_science_bias(instrument, context_date)

def get_next_candle_prediction(instrument, timeframe):
    df = fetch_candles(instrument, timeframe)
    last_row = df.iloc[-2] # Last closed
    analysis = analyze_single_candle(instrument, timeframe, last_row)
    
    return {
        'prediction': analysis['expected_next'],
        'confidence': analysis['confidence_score'],
        'reasoning': f"Identified {analysis['candle_type']} on {timeframe}. Lower TF OFL is {analysis['lower_tf_inside']}.",
        'target_pd_arrays': [], # In production, scan for nearest targets
        'timeframe': timeframe
    }

def timeframe_accuracy_check(instrument, timeframe, lookback_candles=50):
    if lookback_candles < 20:
        lookback_candles = 20
        
    df = fetch_candles(instrument, timeframe)
    # Ensure enough data
    df = df.iloc[-(lookback_candles+1):]
    
    total_signals = 0
    correct = 0
    type_stats = {}
    
    for i in range(len(df) - 1):
        analysis = analyze_single_candle(instrument, timeframe, df.iloc[i])
        ct = analysis['candle_type']
        if ct == 'NEUTRAL': continue
        
        total_signals += 1
        if ct not in type_stats: type_stats[ct] = {'total': 0, 'correct': 0}
        type_stats[ct]['total'] += 1
        
        actual_next = df.iloc[i+1]
        is_up = actual_next['close'] > actual_next['open']
        is_down = actual_next['close'] < actual_next['open']
        
        success = False
        if analysis['expected_next'] == 'CONTINUE_HIGHER' and is_up: success = True
        if analysis['expected_next'] == 'CONTINUE_LOWER' and is_down: success = True
        
        if success:
            correct += 1
            type_stats[ct]['correct'] += 1
            
    accuracy_pct = (correct / total_signals * 100) if total_signals > 0 else 0
    
    return {
        'total_signals': total_signals,
        'correct_predictions': correct,
        'accuracy_pct': round(accuracy_pct, 2),
        'by_type': {k: round(v['correct']/v['total']*100, 2) for k, v in type_stats.items()}
    }

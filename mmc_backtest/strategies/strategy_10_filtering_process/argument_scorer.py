import sys, os
import pandas as pd
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../../..')))

from mmc_backtest.modules.video1_pd_arrays import scan_candles_for_fvgs
from mmc_backtest.modules.video2_market_structure import scan_it_points, determine_trend
from mmc_backtest.modules.video3_4_order_flow import scan_candles_for_ofls
from mmc_backtest.modules.video5_candle_science import calculate_candle_metrics, classify_candle_type
from mmc_backtest.backtest.data_loader import fetch_candles

ARGUMENT_WEIGHTS = {
    # Higher timeframe = stronger argument (Video 4 rule)
    'MONTHLY_OFL_BULLISH':    7,
    'MONTHLY_OFL_BEARISH':    7,
    'WEEKLY_OFL_BULLISH':     6,
    'WEEKLY_OFL_BEARISH':     6,
    'DAILY_OFL_BULLISH':      5,
    'DAILY_OFL_BEARISH':      5,
    '4H_OFL_BULLISH':         4,
    '4H_OFL_BEARISH':         4,
    '1H_OFL_BULLISH':         3,
    '1H_OFL_BEARISH':         3,
    'MONTHLY_CS_BULLISH':     7,
    'MONTHLY_CS_BEARISH':     7,
    'WEEKLY_CS_BULLISH':      6,
    'WEEKLY_CS_BEARISH':      6,
    'DAILY_CS_BULLISH':       5,
    'DAILY_CS_BEARISH':       5,
    'DAILY_FVG_BULLISH':      5,
    'DAILY_FVG_BEARISH':      5,
    '4H_FVG_BULLISH':         4,
    '4H_FVG_BEARISH':         4,
    'DAILY_IT_TREND_BULLISH': 5,
    'DAILY_IT_TREND_BEARISH': 5,
}

def score_instrument(instrument, data_dir=None) -> dict:
    """
    Score an instrument for directional bias using all available
    timeframe data and MMC argument types.
    """
    bullish_score = 0
    bearish_score = 0
    args_bull = []
    args_bear = []

    # --- Check each timeframe for OFL direction ---
    for tf in ['DAILY', '4H', '1H']:
        try:
            df = fetch_candles(instrument, tf, data_dir)
            if df is None or df.empty: continue
            
            ofls = scan_candles_for_ofls(df.tail(500), instrument)
            if ofls:
                most_recent = ofls[0]  # Most recent OFL (assuming sorted desc by time)
                direction   = most_recent['direction']
                weight      = ARGUMENT_WEIGHTS.get(f'{tf}_OFL_{direction}', 0)
                if direction == 'BULLISH':
                    bullish_score += weight
                    args_bull.append(f'{tf} OFL BULLISH (score +{weight}, prob={most_recent["probability_label"]})')
                else:
                    bearish_score += weight
                    args_bear.append(f'{tf} OFL BEARISH (score +{weight}, prob={most_recent["probability_label"]})')
        except Exception:
            pass

    # --- Check DAILY and WEEKLY candle science ---
    for tf in ['DAILY', 'WEEKLY']:
        try:
            df = fetch_candles(instrument, tf, data_dir)
            if df is None or len(df) < 2: continue
            
            last_closed = df.iloc[-2]  # Always use last CLOSED candle
            metrics  = calculate_candle_metrics(
                last_closed['open'], last_closed['high'],
                last_closed['low'],  last_closed['close'])
            cs_type  = classify_candle_type(metrics)

            if cs_type['expected_next'] == 'CONTINUE_HIGHER':
                w = ARGUMENT_WEIGHTS.get(f'{tf}_CS_BULLISH', 5)
                bullish_score += w
                args_bull.append(f'{tf} CANDLE_SCIENCE BULLISH {cs_type["candle_type"]} (score +{w})')
            elif cs_type['expected_next'] == 'CONTINUE_LOWER':
                w = ARGUMENT_WEIGHTS.get(f'{tf}_CS_BEARISH', 5)
                bearish_score += w
                args_bear.append(f'{tf} CANDLE_SCIENCE BEARISH {cs_type["candle_type"]} (score +{w})')
        except Exception:
            pass

    # --- Check DAILY unmitigated FVGs ---
    try:
        df   = fetch_candles(instrument, 'DAILY', data_dir)
        if df is not None and not df.empty:
            fvgs = scan_candles_for_fvgs(df.tail(200), instrument)
            recent_fvgs = [f for f in fvgs
                           if not f.get('is_mitigated', True)
                           and f.get('fvg_type') in ['PFVG', 'BFVG']]
            if recent_fvgs:
                most_recent_fvg = recent_fvgs[-1]
                direction = most_recent_fvg['direction']
                w = ARGUMENT_WEIGHTS.get(f'DAILY_FVG_{direction}', 5)
                if direction == 'BULLISH':
                    bullish_score += w
                    args_bull.append(f'DAILY FVG BULLISH {most_recent_fvg["fvg_type"]} (score +{w})')
                else:
                    bearish_score += w
                    args_bear.append(f'DAILY FVG BEARISH {most_recent_fvg["fvg_type"]} (score +{w})')
    except Exception:
        pass

    # --- Check IT trend direction ---
    try:
        df = fetch_candles(instrument, 'DAILY', data_dir)
        if df is not None and not df.empty:
            it_pts = scan_it_points(df.tail(300))
            trend  = determine_trend(it_pts)
            if trend['trend'] != 'NEUTRAL':
                direction = trend['trend']
                w = ARGUMENT_WEIGHTS.get(f'DAILY_IT_TREND_{direction}', 5)
                if direction == 'BULLISH':
                    bullish_score += w
                    args_bull.append(f'DAILY IT_TREND BULLISH (score +{w})')
                else:
                    bearish_score += w
                    args_bear.append(f'DAILY IT_TREND BEARISH (score +{w})')
    except Exception:
        pass

    # --- Calculate bias ---
    total_score = bullish_score + bearish_score

    if total_score == 0:
        bias_direction = 'NEUTRAL'
        bias_strength  = 'LOW'
    elif bullish_score == 0 and bearish_score > 0:
        bias_direction = 'BEARISH'
        bias_strength  = 'HIGH'
    elif bearish_score == 0 and bullish_score > 0:
        bias_direction = 'BULLISH'
        bias_strength  = 'HIGH'
    else:
        diff_ratio = abs(bullish_score - bearish_score) / total_score
        if bullish_score > bearish_score:
            bias_direction = 'BULLISH'
        else:
            bias_direction = 'BEARISH'
            
        if diff_ratio >= 0.70:
            bias_strength = 'HIGH'
        elif diff_ratio >= 0.40:
            bias_strength = 'MEDIUM'
        else:
            bias_strength = 'LOW'

    # --- Recommendation ---
    if bias_strength == 'HIGH':
        recommendation = f"TRADE {bias_direction} — all arguments align ({bullish_score} vs {bearish_score})"
    elif bias_strength == 'MEDIUM':
        recommendation = f"CAUTION — {bias_direction} bias but mixed arguments ({bullish_score} vs {bearish_score})"
    else:
        recommendation = f"AVOID — arguments too balanced ({bullish_score} vs {bearish_score}). Wait for clearer alignment."

    return {
        'instrument':        instrument,
        'bullish_score':     bullish_score,
        'bearish_score':     bearish_score,
        'total_score':       total_score,
        'bias_direction':    bias_direction,
        'bias_strength':     bias_strength,
        'arguments_bullish': args_bull,
        'arguments_bearish': args_bear,
        'recommendation':    recommendation
    }

def rank_instruments(instruments_list, data_dir=None) -> list[dict]:
    """
    Score all instruments and rank by bias_strength then score gap.
    """
    scores = []
    for inst in instruments_list:
        result = score_instrument(inst, data_dir)
        score_gap = abs(result['bullish_score'] - result['bearish_score'])
        result['score_gap'] = score_gap
        scores.append(result)

    strength_order = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
    scores.sort(key=lambda x: (
        strength_order.get(x['bias_strength'], 0),
        x['score_gap']
    ), reverse=True)

    for rank, item in enumerate(scores, start=1):
        item['rank'] = rank

    return scores

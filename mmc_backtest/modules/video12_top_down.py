import pandas as pd
import numpy as np
from modules.video3_4_order_flow import full_order_flow_scan
from modules.video10_context import full_context_scan

def get_top_down_analysis(instrument, trader_type='FILTERING_PROCESS'):
    """Complete top-down analysis combining ALL modules."""
    bullish_args = 0
    bearish_args = 0
    
    # 1. Weekly OFL bias
    weekly_ofl = full_order_flow_scan(instrument, 'W1')
    if weekly_ofl.get('most_recent_ofl'):
        if weekly_ofl['most_recent_ofl']['direction'] == 'BULLISH': bullish_args += 1
        else: bearish_args += 1
        
    # 2. Daily OFL bias
    daily_ofl = full_order_flow_scan(instrument, 'D1')
    if daily_ofl.get('most_recent_ofl'):
        if daily_ofl['most_recent_ofl']['direction'] == 'BULLISH': bullish_args += 1
        else: bearish_args += 1
        
    # 3. Context Scans (4H and 1H)
    ctx_4h = full_context_scan(instrument, '4H')
    ctx_1h = full_context_scan(instrument, '1H')
    all_ctx = ctx_4h + ctx_1h
    
    for ctx in all_ctx:
        if ctx['direction'] == 'BULLISH': bullish_args += 1
        else: bearish_args += 1
        
    overall_direction = 'NEUTRAL'
    if bullish_args > bearish_args + 1:
        overall_direction = 'BULLISH'
    elif bearish_args > bullish_args + 1:
        overall_direction = 'BEARISH'
        
    readiness = 'NOT_READY'
    if len(all_ctx) > 0:
        readiness = 'LOW'
        if (bullish_args >= 2 and overall_direction == 'BULLISH') or \
           (bearish_args >= 2 and overall_direction == 'BEARISH'):
            readiness = 'MEDIUM'
            # Full system would check news here for HIGH readiness

    summary = f"Instrument {instrument} analyzed. "
    if overall_direction != 'NEUTRAL':
        summary += f"Clear {overall_direction} alignment with {max(bullish_args, bearish_args)} supporting arguments."
    else:
        summary += "Mixed signals across timeframes. Awaiting alignment."

    return {
        'instrument': instrument,
        'trader_type': trader_type,
        'bias': overall_direction,
        'weekly_ofl': weekly_ofl.get('most_recent_ofl'),
        'daily_ofl': daily_ofl.get('most_recent_ofl'),
        'active_contexts': all_ctx,
        'overall_direction': overall_direction,
        'trade_readiness': readiness,
        'summary': summary,
        'arguments_bullish': bullish_args,
        'arguments_bearish': bearish_args
    }

def calculate_session_stats(trade_entries_list):
    """Calculate full backtest statistics from actual trade data."""
    total = len(trade_entries_list)
    if total == 0: return {}
    
    wins = [t for t in trade_entries_list if t.get('result') == 'WIN']
    losses = [t for t in trade_entries_list if t.get('result') == 'LOSS']
    bes = [t for t in trade_entries_list if t.get('result') == 'BREAKEVEN']
    
    wr = (len(wins) / total * 100) if total > 0 else 0
    rr_list = [t.get('rr_achieved', 0) for t in trade_entries_list if t.get('rr_achieved') is not None]
    
    stats = {
        'total_trades': total,
        'wins': len(wins),
        'losses': len(losses),
        'breakevens': len(bes),
        'win_rate': round(float(wr), 2),
        'total_rr': round(float(sum(rr_list)), 2),
        'avg_rr_achieved': round(float(np.mean(rr_list)), 2) if rr_list else 0
    }
    
    return stats

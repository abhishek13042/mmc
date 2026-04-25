import sys, os

# Add project root to path
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../../..')))

try:
    from mmc_backtest.strategies.strategy_10_filtering_process.argument_scorer import rank_instruments
except ImportError:
    try:
        import sys, os
        sys.path.append(os.path.dirname(__file__))
        from argument_scorer import rank_instruments
    except ImportError:
        from .argument_scorer import rank_instruments

def apply_filter_to_signals(signals_list, data_dir=None) -> dict:
    """
    Apply the Filtering Process argument system to any list
    of signals from S1-S9. Accepts and rejects signals based
    on whether instrument bias aligns with signal direction.
    """
    if not signals_list:
        return {
            'accepted': [],
            'rejected': [],
            'filter_stats': {
                'total_signals': 0,
                'accepted_count': 0,
                'rejected_count': 0,
                'acceptance_rate_pct': 0.0,
                'by_instrument': {}
            }
        }

    instruments = list(set(s['instrument'] for s in signals_list))
    rankings     = {r['instrument']: r
                    for r in rank_instruments(instruments, data_dir)}

    accepted = []
    rejected = []

    for sig in signals_list:
        inst   = sig['instrument']
        direction = sig['direction']
        score  = rankings.get(inst, {})
        bias   = score.get('bias_direction', 'NEUTRAL')
        strength = score.get('bias_strength', 'LOW')

        # Arjo's rule: only trade if bias aligns with signal
        # AND strength is HIGH or MEDIUM
        if (bias == direction and strength in ['HIGH', 'MEDIUM']):
            sig['filter_bias']     = bias
            sig['filter_strength'] = strength
            sig['filter_result']   = 'ACCEPTED'
            accepted.append(sig)
        else:
            sig['filter_bias']     = bias
            sig['filter_strength'] = strength
            sig['filter_result']   = 'REJECTED'
            sig['reject_reason']   = f"Signal {direction}, bias {bias} ({strength})"
            rejected.append(sig)

    total = len(signals_list)
    accept_rate = (len(accepted) / total * 100) if total > 0 else 0.0

    by_inst = {}
    for inst in instruments:
        inst_sigs     = [s for s in signals_list if s['instrument'] == inst]
        inst_accepted = [s for s in accepted if s['instrument'] == inst]
        by_inst[inst] = {
            'total':       len(inst_sigs),
            'accepted':    len(inst_accepted),
            'rejected':    len(inst_sigs) - len(inst_accepted),
            'bias':        rankings.get(inst, {}).get('bias_direction', 'N/A'),
            'strength':    rankings.get(inst, {}).get('bias_strength', 'N/A'),
        }

    return {
        'accepted': accepted,
        'rejected': rejected,
        'filter_stats': {
            'total_signals':      total,
            'accepted_count':     len(accepted),
            'rejected_count':     len(rejected),
            'acceptance_rate_pct': round(accept_rate, 2),
            'by_instrument':      by_inst,
        }
    }

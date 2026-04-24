def run_comparison_backtest(strategy_results_before,
                            strategy_results_after) -> dict:
    """
    Compare win rates BEFORE and AFTER applying the filter.
    Shows whether the Filtering Process improves results.
    """
    def calc_stats(trades):
        total = len(trades)
        if total == 0:
            return {'total': 0, 'wins': 0, 'win_rate': 0.0, 'avg_rr': 0.0, 'total_rr': 0.0}
        
        wins  = sum(1 for t in trades if t.get('result') == 'WIN')
        rrs   = [t['rr_achieved'] for t in trades
                  if t.get('rr_achieved') is not None]
        
        return {
            'total':    total,
            'wins':     wins,
            'win_rate': round(wins / total * 100, 2),
            'avg_rr':   round(sum(rrs) / len(rrs), 2) if rrs else 0.0,
            'total_rr': round(sum(r for r in rrs if r > 0), 2)
        }

    before = calc_stats(strategy_results_before)
    after  = calc_stats(strategy_results_after)

    win_rate_improvement = after['win_rate'] - before['win_rate']
    avg_rr_improvement   = after['avg_rr']   - before['avg_rr']

    print("\n" + "="*60)
    print("FILTERING PROCESS IMPACT ANALYSIS")
    print("="*60)
    print(f"BEFORE filter: {before['total']} trades, WR={before['win_rate']}%, Avg RR={before['avg_rr']}")
    print(f"AFTER  filter: {after['total']} trades, WR={after['win_rate']}%, Avg RR={after['avg_rr']}")
    print(f"Improvement:   WR +{win_rate_improvement:.1f}%, RR +{avg_rr_improvement:.2f}")
    print("="*60)

    return {
        'before_filter': before,
        'after_filter':  after,
        'win_rate_improvement': round(win_rate_improvement, 2),
        'avg_rr_improvement':   round(avg_rr_improvement, 2),
        'signals_removed':      before['total'] - after['total'],
        'removal_pct': round(
            (before['total'] - after['total'])
            / before['total'] * 100, 2
        ) if before['total'] > 0 else 0.0
    }

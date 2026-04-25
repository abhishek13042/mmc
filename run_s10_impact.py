import sys, os
from pathlib import Path
import pandas as pd
from datetime import datetime

# Fix paths
THIS_FILE = Path(__file__).resolve()
MMC_ROOT = THIS_FILE.parent / 'mmc_backtest'
PROJECT_ROOT = THIS_FILE.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(MMC_ROOT))

import mmc_backtest.run_all_strategies as master
from mmc_backtest.strategies.strategy_10_filtering_process import argument_scorer, filter_overlay, backtest as s10_logic

def main():
    print("\n" + "="*80)
    print("   MMC STRATEGY 10 — FULL IMPACT ANALYSIS (FILTERED vs UNFILTERED)")
    print("="*80)

    # 1. Run Strategy 1 to get the 'Unfiltered' universe
    master.import_all_strategies()
    print("\n[STEP 1] Generating Strategy 1 signals (Full History)...")
    master.run_strategy_1()
    
    all_trades = []
    for result in master.ALL_BATCH_RESULTS:
        if isinstance(result, dict) and 'trades' in result:
            all_trades.extend(result['trades'])

    if not all_trades:
        print("[ERROR] No trades found. Check data paths.")
        return

    # 2. Apply S10 Filtering
    print("\n[STEP 2] Applying Strategy 10 Institutional Filter...")
    filter_result = filter_overlay.apply_filter_to_signals(all_trades, str(master.DATA_DIR))
    
    # 3. Compare Results
    print("\n[STEP 3] Performance Comparison:")
    comparison = s10_logic.run_comparison_backtest(all_trades, filter_result['accepted'])
    
    # 4. Save results to Strategy 10 folder
    s10_dir = MMC_ROOT / 'strategies' / 'strategy_10_filtering_process' / 'resultsv2'
    s10_dir.mkdir(parents=True, exist_ok=True)
    
    # Save CSVs
    pd.DataFrame(filter_result['accepted']).to_csv(s10_dir / 's10_filtered_trades_accepted.csv', index=False)
    pd.DataFrame(filter_result['rejected']).to_csv(s10_dir / 's10_filtered_trades_rejected.csv', index=False)
    pd.DataFrame([comparison]).to_csv(s10_dir / 's10_impact_analysis.csv', index=False)
    
    # Save a nice results.md
    md_content = f"""# Strategy 10: Filtering Process Impact Report

## 📊 Filter Impact Summary
- **Before Filter**: {comparison['before_filter']['total']} trades | {comparison['before_filter']['win_rate']}% WR | {comparison['before_filter']['avg_rr']} Avg RR
- **After Filter**: {comparison['after_filter']['total']} trades | {comparison['after_filter']['win_rate']}% WR | {comparison['after_filter']['avg_rr']} Avg RR
- **Win Rate Boost**: +{comparison['win_rate_improvement']}%
- **Signal Reduction**: {comparison['removal_pct']}% (removed {comparison['signals_removed']} low-probability signals)

## 🏛️ Bias Rankings
"""
    rankings = argument_scorer.rank_instruments(master.INSTRUMENTS, str(master.DATA_DIR))
    for r in rankings:
        md_content += f"- **{r['instrument']}**: {r['bias_direction']} ({r['bias_strength']}) | Score: {r['bullish_score']} vs {r['bearish_score']}\n"

    with open(s10_dir / 'results.md', 'w') as f:
        f.write(md_content)

    print(f"\n[COMPLETE] Results saved to: {s10_dir}")
    print(f"Win Rate improved from {comparison['before_filter']['win_rate']}% to {comparison['after_filter']['win_rate']}%")

if __name__ == '__main__':
    main()

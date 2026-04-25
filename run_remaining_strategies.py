import sys, os
from pathlib import Path

# Fix paths
THIS_FILE = Path(__file__).resolve()
MMC_ROOT = THIS_FILE.parent / 'mmc_backtest'
PROJECT_ROOT = THIS_FILE.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(MMC_ROOT))

import mmc_backtest.run_all_strategies as master

if __name__ == '__main__':
    master.import_all_strategies()
    master.verify_all_data()
    
    print("\n" + "="*70)
    print("   RUNNING REMAINING STRATEGIES (S3 - S9)")
    print("="*70)

    strategies_to_run = [
        master.run_strategy_3,
        master.run_strategy_4,
        master.run_strategy_5,
        master.run_strategy_6,
        master.run_strategy_7,
        master.run_strategy_8,
        master.run_strategy_9
    ]

    for run_func in strategies_to_run:
        try:
            run_func()
        except Exception as e:
            print(f"[ERROR] Strategy execution failed: {e}")

    best = master.write_best_performers()
    master.print_final_summary(best)

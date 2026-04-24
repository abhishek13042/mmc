import sys
import os
from pathlib import Path

# Fix paths
THIS_FILE = Path(__file__).resolve()
MMC_ROOT = THIS_FILE.parent / 'mmc_backtest'
PROJECT_ROOT = THIS_FILE.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(MMC_ROOT))

# Import the runner logic from the master script
# We need to monkey-patch or just copy the parts we need.
# Actually, it's easier to just call run_strategy_1() if we import it.
import mmc_backtest.run_all_strategies as master

if __name__ == '__main__':
    master.import_all_strategies()
    master.verify_all_data()
    
    print("\n[INFO] Running Strategy 1 Only...")
    master.run_strategy_1()
    
    best = master.write_best_performers()
    master.print_final_summary(best)

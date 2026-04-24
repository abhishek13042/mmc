import sys
import os
from pathlib import Path

MMC_ROOT = Path(r'C:\Users\Admin\OneDrive\Desktop\MMC\mmc_backtest')
PROJECT_ROOT = MMC_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(MMC_ROOT))

from strategies.strategy_8_it_retracement.backtest import run_backtest

print("Running Strategy 8 Test Run (EURUSD 1H)...")
try:
    # Use a small range or just run full if data is small
    res = run_backtest('EURUSD', '1H')
    if 'error' in res:
        print(f"  [FAIL] {res['error']}")
    else:
        print(f"  [OK] Found {res['total_signals']} signals. Win Rate: {res['win_rate_pct']}%")
except Exception as e:
    import traceback
    print(f"  [CRASH] {e}")
    traceback.print_exc()

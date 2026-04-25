import sys, os
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(r"C:\Users\Admin\OneDrive\Desktop\MMC")
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "mmc_backtest"))

from mmc_backtest.strategies.strategy_3_fva_good.backtest import run_backtest

print("Running test backtest for S3...")
res = run_backtest("EURUSD", "H1", data_dir=str(PROJECT_ROOT / "mmc_backtest" / "data" / "raw"))
if res:
    print(f"Success! Found {res['total_signals']} signals.")
else:
    print("Failed to run backtest.")

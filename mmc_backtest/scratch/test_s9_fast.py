import sys
import os
from pathlib import Path
import pandas as pd

MMC_ROOT = Path(r'C:\Users\Admin\OneDrive\Desktop\MMC\mmc_backtest')
PROJECT_ROOT = MMC_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(MMC_ROOT))

from strategies.strategy_9_pch_pcl_sweep.scanner import scan_pch_pcl_sweep
from backtest.data_loader import fetch_candles

print("Running Strategy 9 Fast Test (2000 candles)...")
df = fetch_candles('EURUSD', '1H')
if df is not None:
    test_df = df.tail(2000).copy()
    signals = scan_pch_pcl_sweep(test_df, 'EURUSD', '1H')
    print(f"  [OK] Found {len(signals)} signals in last 2000 candles.")

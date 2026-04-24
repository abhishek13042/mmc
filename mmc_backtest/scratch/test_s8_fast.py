import sys
import os
from pathlib import Path
import pandas as pd

MMC_ROOT = Path(r'C:\Users\Admin\OneDrive\Desktop\MMC\mmc_backtest')
PROJECT_ROOT = MMC_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(MMC_ROOT))

from strategies.strategy_8_it_retracement.scanner import scan_it_retracement
from backtest.data_loader import fetch_candles

print("Running Strategy 8 Fast Test (1000 candles)...")
df = fetch_candles('EURUSD', '1H')
if df is not None:
    # Scan last 1000 candles
    test_df = df.tail(1000).copy()
    signals = scan_it_retracement(test_df, 'EURUSD', '1H')
    print(f"  [OK] Found {len(signals)} signals in last 1000 candles.")

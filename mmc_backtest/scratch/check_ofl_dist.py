import sys
import os
import pandas as pd

# Add project root and mmc_backtest folder to path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
MMC_DIR = os.path.join(ROOT_DIR, 'mmc_backtest')
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, MMC_DIR)

from mmc_backtest.backtest.data_loader import fetch_candles, get_available_data
from mmc_backtest.modules.video3_4_order_flow import scan_candles_for_ofls
from collections import Counter

def check_distribution():
    inv = get_available_data('data/raw')
    for inst in inv:
        for tf in ['DAILY', '4H']:
            try:
                print(f"\n--- {inst} {tf} ---")
                df = fetch_candles(inst, tf, 'data/raw')
                ofls = scan_candles_for_ofls(df, inst)
                labels = [o['probability_label'] for o in ofls]
                print(Counter(labels))
            except Exception as e:
                print(f"Error for {inst} {tf}: {e}")

if __name__ == "__main__":
    check_distribution()

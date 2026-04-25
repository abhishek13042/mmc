import pandas as pd
import os
import numpy as np

results_dir = r"c:\Users\Admin\OneDrive\Desktop\MMC\mmc_backtest\strategies\strategy_1_ofl_continuation\results"
timeframes = ["daily", "4h", "1h", "15m", "5m"]

print("="*60)
print("   MEDIAN RR ANALYSIS PER TIMEFRAME (EURUSD)")
print("="*60)
print(f"{'TF':<10} | {'Median RR (Winners)':<20} | {'Average RR (Winners)':<20}")
print("-" * 60)

for tf in timeframes:
    csv_path = os.path.join(results_dir, f"strategy_1_eurusd_{tf}.csv")
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        # Winning trades only
        wins = df[df['result'] == 'WIN']
        if not wins.empty:
            median_win = wins['rr_achieved'].median()
            avg_win = wins['rr_achieved'].mean()
            print(f"{tf.upper():<10} | {median_win:<20.2f} | {avg_win:<20.2f}")
        else:
            print(f"{tf.upper():<10} | No wins found")
    else:
        print(f"{tf.upper():<10} | File not found")

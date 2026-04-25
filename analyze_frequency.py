import pandas as pd
import os
from datetime import datetime

RESULTS_DIR = r"C:\Users\Admin\OneDrive\Desktop\MMC\mmc_backtest\backtest\results"

def analyze_frequency():
    s1_files = [f for f in os.listdir(RESULTS_DIR) if f.startswith('s1_ofl_') and f.endswith('.csv')]
    
    all_dates = []
    total_signals = 0
    
    for f in s1_files:
        df = pd.read_csv(os.path.join(RESULTS_DIR, f))
        if 'signal_datetime' in df.columns:
            # Convert to datetime and strip time for day counting
            df['date'] = pd.to_datetime(df['signal_datetime']).dt.date
            all_dates.extend(df['date'].tolist())
            total_signals += len(df)
            
    if not all_dates:
        print("No signals found.")
        return
        
    all_dates = sorted(list(set(all_dates)))
    start_date = all_dates[0]
    end_date = all_dates[-1]
    total_days = (end_date - start_date).days + 1
    
    avg_per_day = total_signals / total_days
    
    # Recency check
    last_signal_date = end_date
    days_since_last = (datetime.now().date() - last_signal_date).days
    
    print(f"# Institutional Trade Frequency Analysis")
    print(f"Data Coverage: {start_date} to {end_date} ({total_days} days)")
    print(f"Total Combined Signals (S1): {total_signals}")
    print(f"Average Trades per Day (All Pairs/TFs): {round(avg_per_day, 2)}")
    print(f"Recency: Last trade detected on {last_signal_date} ({days_since_last} days ago)")
    
    # Frequency by Timeframe
    print("\n## Frequency by Timeframe (Avg Per Day)")
    for tf in ['H4', 'H1', 'M15']:
        tf_count = 0
        for f in s1_files:
            if f"_{tf}.csv" in f:
                df = pd.read_csv(os.path.join(RESULTS_DIR, f))
                tf_count += len(df)
        print(f"- **{tf}**: {round(tf_count / total_days, 2)} signals/day")

if __name__ == "__main__":
    analyze_frequency()

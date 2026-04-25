import pandas as pd
import os

MASTER_PATH = r"C:\Users\Admin\OneDrive\Desktop\MMC\mmc_backtest\backtest\results\MASTER_SUMMARY.csv"

def analyze_results():
    if not os.path.exists(MASTER_PATH):
        print(f"Error: {MASTER_PATH} not found.")
        return

    df = pd.read_csv(MASTER_PATH)
    
    # Filter only OK status
    df_ok = df[df['status'] == 'OK'].copy()
    
    if df_ok.empty:
        print("No successful runs found in master summary.")
        return

    # 1. Basic Stats per Strategy/Inst/TF
    summary = df_ok[['strategy', 'instrument', 'timeframe', 'total_signals', 'win_rate_pct', 'avg_rr', 'total_rr']]
    
    # 2. Trade Frequency (Signals per year approx)
    # Assuming the data covers roughly 5 years (common for MT5 exports on lower TFs)
    # or 10-15 years for H1/H4.
    # Let's just calculate signals per day if we had dates, but we don't in the summary.
    # We can use the candle count if we had it, but we only have total_signals.
    
    print("# MMC Institutional Backtest Analysis Report")
    print("\n## Strategy Performance Overview")
    print(summary.to_markdown(index=False))
    
    # 3. Strategy Aggregates
    print("\n## Strategy Aggregates (Average across all pairs)")
    strat_agg = df_ok.groupby('strategy').agg({
        'total_signals': 'sum',
        'win_rate_pct': 'mean',
        'avg_rr': 'mean',
        'total_rr': 'sum'
    }).reset_index()
    print(strat_agg.to_markdown(index=False))

    # 4. Instrument Aggregates
    print("\n## Instrument Aggregates")
    inst_agg = df_ok.groupby('instrument').agg({
        'total_signals': 'sum',
        'win_rate_pct': 'mean',
        'total_rr': 'sum'
    }).reset_index()
    print(inst_agg.to_markdown(index=False))

if __name__ == "__main__":
    analyze_results()

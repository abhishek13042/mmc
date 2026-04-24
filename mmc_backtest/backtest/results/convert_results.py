import json
import pandas as pd
import os

# Paths
results_dir = r"c:\Users\Admin\OneDrive\Desktop\MMC\mmc_backtest\backtest\results"
json_path = os.path.join(results_dir, "strategy_6_eurusd_d1_h1.json")
csv_path = os.path.join(results_dir, "strategy_6_entries.csv")

def convert_json_to_csv():
    if not os.path.exists(json_path):
        print(f"File not found: {json_path}")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)
    
    trades = data.get('trades', [])
    if not trades:
        print("No trades found in JSON.")
        return
        
    df = pd.DataFrame(trades)
    
    # Flatten stats if needed, but trades is usually flat
    # Let's check if there are nested dicts
    if 'checklist_passed' in df.columns:
        # Strategy 7 might have this, Strategy 6 usually doesn't
        pass
        
    df.to_csv(csv_path, index=False)
    print(f"Successfully exported {len(df)} entries to {csv_path}")

if __name__ == "__main__":
    convert_json_to_csv()

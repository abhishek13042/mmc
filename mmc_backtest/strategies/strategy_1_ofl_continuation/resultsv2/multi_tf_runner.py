import pandas as pd
import numpy as np
import os
import time
import matplotlib.pyplot as plt
from backtestv2 import load_data, run_s1_backtest, build_ai_dataset, CONFIG

# Timeframe mapping
TIMEFRAMES = {
    "DAILY": "EURUSD1440.csv",
    "4H": "EURUSD240.csv",
    "1H": "EURUSD60.csv",
    "15M": "EURUSD15.csv",
    "5M": "EURUSD5.csv"
}

def calculate_metrics(rr_series):
    if len(rr_series) == 0:
        return {"RR": "+0.00", "WR": "0.00%", "PF": "0.00", "MDD": "0.00R", "Sharpe": "0.00"}
    
    total_rr = rr_series.sum()
    win_rate = (rr_series > 0).mean() * 100
    
    # Profit Factor
    pos = rr_series[rr_series > 0].sum()
    neg = abs(rr_series[rr_series < 0].sum())
    pf = pos / neg if neg != 0 else pos
    
    # Max Drawdown
    cum_rr = rr_series.cumsum()
    peak = cum_rr.cummax()
    drawdown = peak - cum_rr
    mdd = drawdown.max()
    
    # Sharpe (approximate, using 1% risk per trade)
    sharpe = (rr_series.mean() / rr_series.std()) * np.sqrt(252) if len(rr_series) > 1 and rr_series.std() != 0 else 0
    
    return {
        "RR": f"+{total_rr:.2f}",
        "WR": f"{win_rate:.2f}%",
        "PF": f"{pf:.2f}",
        "MDD": f"{mdd:.2f}R",
        "Sharpe": f"{sharpe:.2f}"
    }

def run_multi_tf_v2():
    results = []
    
    print("="*80)
    print("      STRATEGY 1 v2 DETAILED FINANCIAL ANALYSIS (MULTI-TIMEFRAME)")
    print("="*80)
    
    for tf_name, filename in TIMEFRAMES.items():
        path = os.path.join(r"c:\Users\Admin\OneDrive\Desktop\MMC\mmc_backtest\data\raw", filename)
        if not os.path.exists(path): continue
            
        print(f"[*] Analyzing {tf_name}...")
        df = load_data(path)
        trades = run_s1_backtest(df, "EURUSD")
        if not trades: continue
        ai_df = build_ai_dataset(df, trades)
        
        # Optimization Filter (Simulating Tier 1 & Tier 4)
        if tf_name == "DAILY":
            opt_df = ai_df[ai_df['volatility_ratio'] > 0.8]
        else:
            # Multi-Session Filter (London or NY)
            opt_df = ai_df[(ai_df['london_session'] == 1) | (ai_df['ny_session'] == 1)]
            # Momentum Quality Filter (Tier 1 style)
            threshold = opt_df['avg_candle_body_pips'].median()
            opt_df = opt_df[opt_df['avg_candle_body_pips'] > threshold]
            
        base_m = calculate_metrics(ai_df['rr_achieved'])
        opt_m = calculate_metrics(opt_df['rr_achieved'])
        
        results.append({
            "TF": tf_name,
            "Signals": f"{len(ai_df)} -> {len(opt_df)}",
            "WinRate": f"{base_m['WR']} -> {opt_m['WR']}",
            "TotalRR": f"{base_m['RR']} -> {opt_m['RR']}",
            "ProfitFactor": f"{base_m['PF']} -> {opt_m['PF']}",
            "MaxDD": f"{base_m['MDD']} -> {opt_m['MDD']}",
            "Sharpe": f"{base_m['Sharpe']} -> {opt_m['Sharpe']}"
        })
        
        # Save Plot for this TF
        plt.figure(figsize=(10, 5))
        plt.style.use('dark_background')
        plt.plot(ai_df['rr_achieved'].cumsum().values, label='Baseline', color='gray', alpha=0.5)
        plt.plot(opt_df['rr_achieved'].cumsum().values, label='v2.0 (Optimized)', color='cyan', linewidth=2)
        plt.title(f"Equity Curve: {tf_name} (EURUSD)")
        plt.legend()
        plt.savefig(os.path.join(CONFIG["results_dir"], f"equity_{tf_name}.png"))
        plt.close()
        
    # Create Summary Table
    report_df = pd.DataFrame(results)
    print("\n" + "="*100)
    print("                      DETAILED INSTITUTIONAL COMPARISON: BASELINE vs v2.0")
    print("="*100)
    print(report_df.to_string(index=False))
    
    # Save results
    os.makedirs(CONFIG["results_dir"], exist_ok=True)
    report_df.to_csv(os.path.join(CONFIG["results_dir"], "financial_analysis_v2.csv"), index=False)
    
    # Generate Markdown Table for User
    md_header = "## Strategy 1 v2.0: Multi-Timeframe Institutional Analysis\n"
    md_header += f"**Generated on**: {time.ctime()}\n\n"
    md_table = report_df.to_markdown(index=False)
    
    with open(os.path.join(CONFIG["results_dir"], "financial_analysis_v2.md"), "w") as f:
        f.write(md_header + md_table + "\n\n### Timeframe Equity Curves\n")
        for r in results:
            f.write(f"#### {r['TF']} Performance\n![{r['TF']} Equity](equity_{r['TF']}.png)\n\n")
        
    print(f"\n[+] Full Multi-TF Report + Plots generated in {CONFIG['results_dir']}")

if __name__ == "__main__":
    run_multi_tf_v2()

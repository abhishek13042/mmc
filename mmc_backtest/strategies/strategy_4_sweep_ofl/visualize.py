import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import os
import json
import argparse

def plot_equity_curve(results, save_path=None):
    trades = results['trades']
    if not trades: return
    r_multiples = [t['rr_achieved'] for t in trades]
    cumulative_r = np.cumsum(r_multiples)
    plt.figure(figsize=(10, 5)); plt.style.use('dark_background')
    plt.plot(cumulative_r, color='#e67e22', linewidth=2, label='S4 Sweep+OFL Equity (R)')
    plt.axhline(0, color='white', linestyle='--', alpha=0.5)
    plt.title(f"S4 Sweep+OFL | {results['instrument']} {results['timeframe']}")
    plt.legend()
    if save_path: plt.savefig(save_path.replace('.png', '_equity.png'))
    else: plt.show()

def plot_sweep_wick_distribution(results, save_path=None):
    """
    Histogram of sweep_wick_pips across all signals.
    """
    trades = results['trades']
    if not trades: return
    wicks = [t['sweep_wick_pips'] for t in trades]
    
    plt.figure(figsize=(10, 6)); plt.style.use('dark_background')
    plt.hist(wicks, bins=15, color='#e67e22', alpha=0.7, edgecolor='white')
    
    mean_wick = np.mean(wicks)
    plt.axvline(mean_wick, color='red', linestyle='--', linewidth=2, label=f'Mean: {mean_wick:.2f} pips')
    
    plt.title("Sweep Wick Size Distribution | S4 Sweep+OFL", fontsize=14)
    plt.xlabel("Wick Size (Pips)"); plt.ylabel("Count")
    plt.legend(); plt.grid(True, alpha=0.1)
    
    if save_path: plt.savefig(save_path.replace('.png', '_wick_dist.png'))
    else: plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MMC Strategy 4 Visualization')
    parser.add_argument('--file', type=str, required=True, help='Path to result JSON')
    parser.add_argument('--save', type=str, help='Base path for plots')
    args = parser.parse_args()
    if os.path.exists(args.file):
        with open(args.file, 'r') as f:
            data = json.load(f)
            plot_equity_curve(data, args.save)
            plot_sweep_wick_distribution(data, args.save)
    else:
        print(f"File not found: {args.file}")

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
    plt.plot(cumulative_r, color='#2ecc71', linewidth=2, label='S5 Candle Science Equity (R)')
    plt.axhline(0, color='white', linestyle='--', alpha=0.5)
    plt.title(f"S5 Candle Science | {results['instrument']} {results['htf']}->{results['ltf']}")
    plt.legend()
    if save_path: plt.savefig(save_path.replace('.png', '_equity.png'))
    else: plt.show()

def plot_htf_candle_type_breakdown(results, save_path=None):
    """
    Pie chart of HTF candle types.
    """
    dist = results['stats'].get('htf_candle_type_distribution', {})
    if not dist: return
    
    labels = list(dist.keys())
    sizes = list(dist.values())
    
    # Map types to colors
    color_map = {
        'DISRESPECT_BULLISH': '#2ecc71', # green
        'DISRESPECT_BEARISH': '#e74c3c', # red
        'RESPECT_BULLISH': '#00ffff',    # cyan
        'RESPECT_BEARISH': '#e67e22'     # orange
    }
    colors = [color_map.get(l, '#95a5a6') for l in labels]
    
    plt.figure(figsize=(8, 8)); plt.style.use('dark_background')
    plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=140, textprops={'color':"w"})
    plt.title("HTF Candle Science Signal Types | S5", fontsize=14)
    
    if save_path: plt.savefig(save_path.replace('.png', '_htf_dist.png'))
    else: plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MMC Strategy 5 Visualization')
    parser.add_argument('--file', type=str, required=True, help='Path to result JSON')
    parser.add_argument('--save', type=str, help='Base path for plots')
    args = parser.parse_args()
    if os.path.exists(args.file):
        with open(args.file, 'r') as f:
            data = json.load(f)
            plot_equity_curve(data, args.save)
            plot_htf_candle_type_breakdown(data, args.save)
    else:
        print(f"File not found: {args.file}")

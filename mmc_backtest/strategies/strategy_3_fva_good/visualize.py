import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import os
import json
import argparse

def plot_equity_curve(results, save_path=None):
    trades = results['trades']
    if not trades:
        print("No trades to plot.")
        return
        
    r_multiples = [t['rr_achieved'] for t in trades]
    cumulative_r = np.cumsum(r_multiples)
    
    plt.figure(figsize=(10, 5))
    plt.style.use('dark_background')
    plt.plot(cumulative_r, color='#3498db', linewidth=2, label='S3 Good FVA Equity (R)')
    plt.axhline(0, color='white', linestyle='--', alpha=0.5)
    plt.title(f"S3 Good FVA | {results['instrument']} {results['timeframe']}")
    plt.xlabel("Trade Number")
    plt.ylabel("Cumulative R")
    plt.legend()
    if save_path:
        plt.savefig(save_path.replace('.png', '_equity.png'))
    else:
        plt.show()

def plot_win_loss_distribution(results, save_path=None):
    stats = results['stats']
    labels = ['Wins', 'Losses', 'Neutrals']
    counts = [stats['wins'], stats['losses'], stats['neutrals']]
    colors = ['#2ecc71', '#e74c3c', '#95a5a6']
    
    plt.figure(figsize=(6, 5))
    plt.style.use('dark_background')
    plt.bar(labels, counts, color=colors)
    plt.title(f"S3 Win/Loss Distribution")
    if save_path:
        plt.savefig(save_path.replace('.png', '_dist.png'))
    else:
        plt.show()

def plot_candle_science_breakdown(results, save_path=None):
    """
    Pie chart showing distribution of candle science signal types.
    """
    cs_dist = results.get('candle_science_distribution', {})
    if not cs_dist:
        print("No candle science data available.")
        return
        
    labels = list(cs_dist.keys())
    sizes = list(cs_dist.values())
    
    # Map colors
    color_map = {
        'BULLISH_HIGH': 'green',
        'BULLISH_MEDIUM': 'lightgreen',
        'BEARISH_HIGH': 'red',
        'BEARISH_MEDIUM': 'salmon',
        'NEUTRAL_LOW': 'grey'
    }
    colors = [color_map.get(label, 'grey') for label in labels]

    plt.figure(figsize=(8, 8))
    plt.style.use('dark_background')
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', colors=colors, startangle=140)
    plt.title("Candle Science Bias Distribution")
    
    if save_path:
        plt.savefig(save_path.replace('.png', '_cs_pie.png'))
    else:
        plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MMC Strategy 3 Visualization')
    parser.add_argument('--file', type=str, required=True, help='Path to result JSON')
    parser.add_argument('--save', type=str, help='Base path for plots')
    
    args = parser.parse_args()
    
    if os.path.exists(args.file):
        with open(args.file, 'r') as f:
            data = json.load(f)
            plot_equity_curve(data, args.save)
            plot_win_loss_distribution(data, args.save)
            plot_candle_science_breakdown(data, args.save)
    else:
        print(f"File not found: {args.file}")

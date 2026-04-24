import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import os
import json
import argparse

def plot_equity_curve(results, save_path=None):
    """
    Plots the cumulative R-multiple (equity) over trade index.
    """
    trades = results['trades']
    if not trades:
        print("No trades to plot.")
        return
        
    r_multiples = [t['rr_achieved'] for t in trades]
    cumulative_r = np.cumsum(r_multiples)
    
    plt.figure(figsize=(12, 6))
    plt.style.use('dark_background')
    
    plt.plot(cumulative_r, color='#00ff00', linewidth=2, label='Strategy Equity (R)')
    plt.axhline(0, color='white', linestyle='--', alpha=0.5)
    
    plt.fill_between(range(len(cumulative_r)), cumulative_r, 0, 
                     where=(cumulative_r >= 0), color='green', alpha=0.2)
    plt.fill_between(range(len(cumulative_r)), cumulative_r, 0, 
                     where=(cumulative_r < 0), color='red', alpha=0.2)
    
    plt.title(f"Strategy 1 - OFL Continuation | {results['instrument']} {results['timeframe']}", fontsize=14)
    plt.xlabel("Trade Number")
    plt.ylabel("Cumulative R")
    plt.grid(True, alpha=0.2)
    plt.legend()
    
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path)
        print(f"Equity curve saved to: {save_path}")
    else:
        plt.show()

def plot_win_loss_distribution(results, save_path=None):
    stats = results['stats']
    labels = ['Wins', 'Losses', 'Neutrals']
    counts = [stats['wins'], stats['losses'], stats['neutrals']]
    colors = ['#2ecc71', '#e74c3c', '#95a5a6']
    
    plt.figure(figsize=(8, 6))
    plt.style.use('dark_background')
    
    bars = plt.bar(labels, counts, color=colors)
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                 f'{int(height)}', ha='center', va='bottom', fontsize=12)
                 
    plt.title(f"Win Rate: {stats['win_rate_pct']}%", fontsize=14)
    plt.ylabel("Number of Trades")
    
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path)
    else:
        plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MMC Strategy 1 Visualization')
    parser.add_argument('--file', type=str, required=True, help='Path to result JSON')
    parser.add_argument('--save', type=str, help='Path to save plot image')
    
    args = parser.parse_args()
    
    if os.path.exists(args.file):
        with open(args.file, 'r') as f:
            data = json.load(f)
            plot_equity_curve(data, args.save)
    else:
        print(f"File not found: {args.file}")

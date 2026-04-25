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
    
    plt.plot(cumulative_r, color='#ffd700', linewidth=2, label='S2 FVA Ideal Equity (R)')
    plt.axhline(0, color='white', linestyle='--', alpha=0.5)
    
    plt.fill_between(range(len(cumulative_r)), cumulative_r, 0, 
                     where=(cumulative_r >= 0), color='gold', alpha=0.1)
    
    plt.title(f"S2 FVA Ideal | Triple Probability | {results['instrument']} {results['timeframe']}", fontsize=14)
    plt.xlabel("Trade Number")
    plt.ylabel("Cumulative R")
    plt.grid(True, alpha=0.1)
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
    colors = ['#f1c40f', '#e74c3c', '#95a5a6'] # Gold for wins
    
    plt.figure(figsize=(8, 6))
    plt.style.use('dark_background')
    
    bars = plt.bar(labels, counts, color=colors)
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                 f'{int(height)}', ha='center', va='bottom', fontsize=12)
                 
    plt.title(f"S2 FVA Ideal | Win Rate: {stats['win_rate_pct']}%", fontsize=14)
    plt.ylabel("Number of Trades")
    
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path)
    else:
        plt.show()

def plot_signal_on_price(df, signal, save_path=None):
    """
    Plots a specific signal on the price chart with FVA zone.
    """
    plt.figure(figsize=(15, 8))
    plt.style.use('dark_background')
    
    # Take a slice around the signal
    sig_dt = signal['signal_datetime']
    idx = df.index[df['datetime'] == sig_dt].tolist()[0]
    plot_df = df.iloc[max(0, idx-50):min(len(df), idx+50)]
    
    plt.plot(plot_df['datetime'], plot_df['close'], color='white', alpha=0.7, label='Price')
    
    # Highlight FVA Zone
    fva_high = signal['fva_high']
    fva_low = signal['fva_low']
    plt.axhspan(fva_low, fva_high, alpha=0.15, color='gold', label='FVA Zone')
    
    # Signal point
    plt.scatter(sig_dt, signal['entry_price'], color='cyan', s=100, marker='o', label='Signal Entry', zorder=5)
    
    # SL and TP levels
    plt.axhline(signal['stop_loss'], color='red', linestyle='--', alpha=0.5, label='SL')
    plt.axhline(signal['tp_4r'], color='green', linestyle='--', alpha=0.5, label='TP Target')
    
    plt.title(f"S2 Signal: {signal['direction']} | {signal['instrument']} {signal['timeframe']} | {sig_dt}")
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path)
    else:
        plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MMC Strategy 2 Visualization')
    parser.add_argument('--file', type=str, required=True, help='Path to result JSON')
    parser.add_argument('--save', type=str, help='Path to save plot image')
    
    args = parser.parse_args()
    
    if os.path.exists(args.file):
        with open(args.file, 'r') as f:
            data = json.load(f)
            plot_equity_curve(data, args.save)
    else:
        print(f"File not found: {args.file}")

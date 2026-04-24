import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import os
import json
import argparse

def plot_equity_curve(results, save_path=None):
    trades = results.get('trades', [])
    if not trades:
        print("No trades to plot.")
        return
        
    # Calculate R-multiple per trade
    # WIN = 2R (or more if context target is further), LOSS = -1R
    r_multiples = []
    for t in trades:
        if t['outcome'] == 'WIN':
            # Context target is at least 2R
            risk = t['risk_pips']
            if risk > 0:
                reward = abs(t['entry_price'] - t['exit_price']) * (t['tp_2r'] - t['entry_price'])/(t['tp_2r'] - t['entry_price']) # Mock multiplier
                # Actually, let's just calculate it properly
                reward_pips = abs(t['entry_price'] - t['exit_price']) * (t['risk_pips'] / abs(t['entry_price'] - t['stop_loss']))
                r_multiples.append(reward_pips / risk)
            else:
                r_multiples.append(2.0)
        elif t['outcome'] == 'LOSS':
            r_multiples.append(-1.0)
        else:
            r_multiples.append(0.0)
            
    cumulative_r = np.cumsum(r_multiples)
    
    plt.figure(figsize=(12, 6))
    plt.style.use('dark_background')
    
    plt.plot(cumulative_r, color='#00ff00', linewidth=2, label='Equity (R)')
    plt.axhline(0, color='white', linestyle='--', alpha=0.5)
    
    plt.title(f"S6 Sharp Turn Equity Curve | {results['instrument']}", fontsize=14)
    plt.xlabel("Trade Number")
    plt.ylabel("Cumulative R")
    plt.grid(True, alpha=0.2)
    plt.legend()
    
    if save_path:
        plt.savefig(save_path)
    else:
        plt.show()

def plot_win_loss_distribution(results, save_path=None):
    labels = ['Wins', 'Losses', 'Neutrals']
    counts = [results['wins'], results['losses'], results['neutrals']]
    colors = ['#2ecc71', '#e74c3c', '#95a5a6']
    
    plt.figure(figsize=(8, 6))
    plt.style.use('dark_background')
    
    plt.bar(labels, counts, color=colors)
    plt.title(f"Trade Outcomes | Win Rate: {results['win_rate_pct']}%", fontsize=14)
    
    if save_path:
        plt.savefig(save_path)
    else:
        plt.show()

def plot_context_hit_vs_tp2r(results, save_path=None):
    """
    Pie chart: "Context Target Hit" vs "TP2R Only Hit" among all wins.
    Colors: gold (context hit), cyan (tp2r only).
    """
    wins = [t for t in results['trades'] if t['outcome'] == 'WIN']
    if not wins:
        print("No wins to plot.")
        return
        
    context_hits = len([w for w in wins if w['win_type'] == 'CONTEXT'])
    tp2r_hits = len([w for w in wins if w['win_type'] == 'TP2R'])
    
    labels = ['Context Target Hit', 'TP2R Only Hit']
    sizes = [context_hits, tp2r_hits]
    colors = ['gold', 'cyan']
    
    plt.figure(figsize=(8, 8))
    plt.style.use('dark_background')
    
    plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=140, textprops={'color':"w"})
    plt.title("Win Type Breakdown | S6 Sharp Turn", fontsize=14, color="w")
    
    if save_path:
        plt.savefig(save_path)
    else:
        plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MMC Strategy 6 Visualization')
    parser.add_argument('--file', type=str, default='c:/Users/Admin/OneDrive/Desktop/MMC/mmc_backtest/backtest/results/s6_EURUSD_D_1H.json')
    
    args = parser.parse_args()
    
    if os.path.exists(args.file):
        with open(args.file, 'r') as f:
            data = json.load(f)
            
        print("Generating plots...")
        plot_equity_curve(data)
        plot_win_loss_distribution(data)
        plot_context_hit_vs_tp2r(data)
    else:
        print(f"Result file not found: {args.file}")

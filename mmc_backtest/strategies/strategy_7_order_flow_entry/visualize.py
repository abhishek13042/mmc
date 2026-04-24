import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import os
import json
import argparse
from collections import Counter

def plot_equity_curve(results, save_path=None):
    trades = results.get('trades', [])
    if not trades: return
    r_multiples = [2.0 if t['outcome'] == 'WIN' else -1.0 if t['outcome'] == 'LOSS' else 0.0 for t in trades]
    cumulative_r = np.cumsum(r_multiples)
    plt.figure(figsize=(12, 6))
    plt.style.use('dark_background')
    plt.plot(cumulative_r, color='#00ff00', linewidth=2)
    plt.axhline(0, color='white', linestyle='--', alpha=0.5)
    plt.title(f"S7 Order Flow Entry Equity | {results['instrument']}", fontsize=14)
    plt.xlabel("Trade Number")
    plt.ylabel("Cumulative R")
    if save_path: plt.savefig(save_path)
    else: plt.show()

def plot_checklist_failures(results, save_path=None):
    """
    Horizontal bar chart of checklist item failures/warnings.
    """
    trades = results.get('trades', [])
    if not trades: return
    
    # Item mapping from video11
    item_map = {
        1: 'DIRECTION', 2: 'NARRATIVE', 3: 'FVG QUALITY', 4: 'FVA QUALITY',
        5: 'HTF TIME', 6: 'LTF TIME', 7: 'CONTEXT', 8: 'ENTRY TF',
        9: 'CONFIRMATION', 10: 'BIG THREE'
    }
    
    hard_items = ['DIRECTION', 'NARRATIVE', 'FVG QUALITY', 'FVA QUALITY', 'CONTEXT', 'ENTRY TF', 'CONFIRMATION']
    warn_items = ['HTF TIME', 'LTF TIME', 'BIG THREE']
    
    all_fails = []
    all_warns = []
    
    for t in trades:
        all_fails.extend(t['checklist_failed_items'])
        all_warns.extend(t['checklist_warn_items'])
        
    fail_counts = Counter(all_fails)
    warn_counts = Counter(all_warns)
    
    labels = list(item_map.values())
    counts = []
    colors = []
    
    for label in labels:
        if label in hard_items:
            counts.append(fail_counts[label])
            colors.append('red')
        else:
            counts.append(warn_counts[label])
            colors.append('orange')
            
    plt.figure(figsize=(10, 8))
    plt.style.use('dark_background')
    
    plt.barh(labels, counts, color=colors)
    plt.title("MMC Checklist Failure Analysis | S7 Order Flow", fontsize=14)
    plt.xlabel("Count of Signals")
    plt.grid(axis='x', alpha=0.2)
    
    if save_path: plt.savefig(save_path)
    else: plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='MMC Strategy 7 Visualization')
    parser.add_argument('--file', type=str, default='c:/Users/Admin/OneDrive/Desktop/MMC/mmc_backtest/backtest/results/s7_EURUSD_D_15M.json')
    args = parser.parse_args()
    
    if os.path.exists(args.file):
        with open(args.file, 'r') as f:
            data = json.load(f)
        plot_equity_curve(data)
        plot_checklist_failures(data)
    else:
        print(f"Result file not found: {args.file}")

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import os

def plot_equity_curve(results_dict, save_path=None):
    """Cumulative RR over trade number."""
    trades = results_dict.get('trades', [])
    if not trades: return
    
    rr_vals = [t['rr_achieved'] for t in trades]
    cumulative_rr = np.cumsum(rr_vals)
    
    plt.figure(figsize=(10, 6))
    plt.plot(cumulative_rr, marker='o', linestyle='-', color='purple')
    plt.title(f"Strategy 9 - PCH/PCL Sweep | {results_dict['instrument']} {results_dict['timeframe']}")
    plt.xlabel("Trade Number")
    plt.ylabel("Cumulative RR")
    plt.grid(True, alpha=0.3)
    
    if save_path:
        plt.savefig(save_path)
        plt.close()
    else:
        plt.show()

def plot_win_loss_distribution(results_dict, save_path=None):
    """Bar chart: Wins vs Losses vs Neutral + win rate %."""
    wins = results_dict['wins']
    losses = results_dict['losses']
    neutrals = results_dict['neutrals']
    
    labels = ['Wins', 'Losses', 'Neutrals']
    counts = [wins, losses, neutrals]
    colors = ['green', 'red', 'gray']
    
    plt.figure(figsize=(8, 5))
    bars = plt.bar(labels, counts, color=colors)
    plt.title(f"Win/Loss Distribution (WR: {results_dict['win_rate_pct']}%)")
    plt.ylabel("Count")
    
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                 f'{int(height)}', ha='center', va='bottom')
                 
    if save_path:
        plt.savefig(save_path)
        plt.close()
    else:
        plt.show()

def plot_signal_on_price(df, signal_dict, lookback=50, save_path=None):
    """Price chart with entry/SL/TP marked."""
    sig_dt = pd.to_datetime(signal_dict['signal_datetime'])
    idx_list = df.index[df['datetime'] == sig_dt].tolist()
    if not idx_list: return
    
    idx = idx_list[0]
    start_idx = max(0, idx - lookback)
    end_idx = min(len(df), idx + 50)
    
    plot_df = df.iloc[start_idx:end_idx]
    
    plt.figure(figsize=(12, 7))
    plt.plot(plot_df['datetime'], plot_df['close'], color='black', alpha=0.5)
    
    # Entry, SL, TP
    plt.axhline(y=signal_dict['entry_price'], color='blue', linestyle='--', label='Entry')
    plt.axhline(y=signal_dict['stop_loss'], color='red', linestyle='--', label='SL')
    plt.axhline(y=signal_dict['tp_2r'], color='green', linestyle=':', label='TP 2R')
    
    # Swept Level
    plt.axhline(y=signal_dict['swept_level'], color='orange', linestyle='-.', label='Swept Level')
    
    # Signal Candle
    plt.scatter(sig_dt, signal_dict['entry_price'], color='orange', s=100, zorder=5)
    
    plt.title(f"S9 {signal_dict['sweep_type']} Sweep: {signal_dict['direction']} @ {signal_dict['signal_datetime']}")
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path)
        plt.close()
    else:
        plt.show()

def plot_pch_vs_pcl_comparison(results_dict, save_path=None):
    """
    Side-by-side comparison: PCH sweeps vs PCL sweeps.
    2 bar groups: Win Rate % and Trade Count.
    Title: "PCH vs PCL Sweep Performance Comparison"
    """
    trades = results_dict.get('trades', [])
    if not trades: return
    
    pch = [t for t in trades if t.get('sweep_type') == 'PCH']
    pcl = [t for t in trades if t.get('sweep_type') == 'PCL']
    
    pch_wr = results_dict['pch_win_rate']
    pcl_wr = results_dict['pcl_win_rate']
    
    labels = ['PCH Sweeps', 'PCL Sweeps']
    wr_vals = [pch_wr, pcl_wr]
    counts = [len(pch), len(pcl)]
    
    x = np.arange(len(labels))
    width = 0.35
    
    fig, ax1 = plt.subplots(figsize=(10, 6))
    
    # Win Rate bars
    rects1 = ax1.bar(x - width/2, wr_vals, width, label='Win Rate %', color='skyblue')
    ax1.set_ylabel('Win Rate %')
    ax1.set_title('PCH vs PCL Sweep Performance Comparison')
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    ax1.set_ylim(0, 100)
    ax1.legend(loc='upper left')
    
    # Trade Count bars (on secondary axis)
    ax2 = ax1.twinx()
    rects2 = ax2.bar(x + width/2, counts, width, label='Trade Count', color='salmon')
    ax2.set_ylabel('Trade Count')
    ax2.legend(loc='upper right')
    
    plt.grid(axis='y', alpha=0.3)
    
    if save_path:
        plt.savefig(save_path)
        plt.close()
    else:
        plt.show()

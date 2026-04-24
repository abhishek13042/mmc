import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import os

def plot_equity_curve(results, save_path=None):
    trades = results['trades']
    if not trades: return
    r_multiples = [t['rr_achieved'] for t in trades]
    cumulative_r = np.cumsum(r_multiples)
    plt.figure(figsize=(10, 5))
    plt.style.use('dark_background')
    plt.plot(cumulative_r, color='#e67e22', linewidth=2, label='Sweep Strategy Equity (R)')
    plt.axhline(0, color='white', linestyle='--', alpha=0.3)
    plt.title(f"Strategy 3 - Sweep Reversal | {results['instrument']} {results['timeframe']}")
    plt.ylabel("Cumulative R")
    if save_path: plt.savefig(save_path)
    plt.show()

def plot_sweep_signal(df, signal, lookback=30, save_path=None):
    """
    Plots the sweep event on the price chart.
    """
    signal_dt = signal['signal_datetime']
    idx = df[df['datetime'] == signal_dt].index[0]
    start = max(0, idx - lookback); end = min(len(df), idx + 20)
    plot_df = df.iloc[start:end].copy()
    plt.figure(figsize=(12, 6))
    plt.style.use('dark_background')
    x = range(len(plot_df))
    plt.vlines(x, plot_df['low'], plot_df['high'], color='white', alpha=0.5)
    plt.plot(x, plot_df['close'], color='white', alpha=0.2)
    
    # Sweep Point
    signal_x = idx - start
    plt.axhline(signal['swept_level'], color='yellow', linestyle=':', label='Swept Level')
    plt.scatter(signal_x, signal['entry_price'], color='orange', s=120, zorder=5, label='Entry (Close)')
    
    # SL/TP
    plt.axhline(signal['stop_loss'], color='red', linestyle='--', label='SL')
    plt.axhline(signal['tp_target'], color='green', linestyle='--', label='Structural Target')
    
    plt.title(f"Liquidity Sweep Reversal: {signal['direction']} at {signal_dt}")
    plt.legend()
    if save_path: plt.savefig(save_path)
    plt.show()

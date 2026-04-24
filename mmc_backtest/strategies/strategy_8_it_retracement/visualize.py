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
    plt.plot(cumulative_rr, marker='o', linestyle='-', color='blue')
    plt.title(f"Strategy 8 - IT Retracement | {results_dict['instrument']} {results_dict['timeframe']}")
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
    plt.axhline(y=signal_dict['tp_4r'], color='green', linestyle='--', label='TP Target')
    
    # Signal Candle
    plt.scatter(sig_dt, signal_dict['entry_price'], color='orange', s=100, zorder=5)
    
    plt.title(f"S8 Signal: {signal_dict['direction']} @ {signal_dict['signal_datetime']}")
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path)
        plt.close()
    else:
        plt.show()

def plot_candles_to_entry_distribution(results_dict, save_path=None):
    """
    4th chart specific to S8:
    Histogram of candles_since_break distribution.
    X axis: 1 to 15 (candles since IT break).
    Y axis: trade count.
    Color bars green if win_rate for that bucket > 50%, red if below.
    Title: "Entry Timing Distribution — Faster = Better?"
    """
    trades = results_dict.get('trades', [])
    if not trades: return
    
    data = []
    for t in trades:
        data.append({
            'candles': t.get('candles_since_break', 0),
            'win': 1 if t['result'] == 'WIN' else 0,
            'loss': 1 if t['result'] == 'LOSS' else 0
        })
    
    df_stats = pd.DataFrame(data)
    if df_stats.empty: return
    
    grouped = df_stats.groupby('candles').agg({'win': 'sum', 'loss': 'sum', 'candles': 'count'}).rename(columns={'candles': 'total'})
    grouped['win_rate'] = grouped['win'] / (grouped['win'] + grouped['loss'])
    
    # Ensure all 1-15 are present
    all_candles = pd.DataFrame({'candles': range(1, 16)})
    grouped = all_candles.merge(grouped, on='candles', how='left').fillna(0)
    
    colors = ['green' if wr > 0.5 else 'red' for wr in grouped['win_rate']]
    
    plt.figure(figsize=(10, 6))
    plt.bar(grouped['candles'], grouped['total'], color=colors, alpha=0.7)
    plt.title("Entry Timing Distribution — Faster = Better?")
    plt.xlabel("Candles Since IT Break")
    plt.ylabel("Number of Trades")
    plt.xticks(range(1, 16))
    plt.grid(axis='y', alpha=0.3)
    
    if save_path:
        plt.savefig(save_path)
        plt.close()
    else:
        plt.show()

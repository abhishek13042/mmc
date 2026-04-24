import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import os

def plot_before_after_comparison(comparison_dict, save_path=None):
    """
    Side-by-side bar chart: Win Rate and Avg RR before vs after filter.
    """
    labels = ['Win Rate %', 'Avg RR']
    before_vals = [comparison_dict['before_filter']['win_rate'], comparison_dict['before_filter']['avg_rr']]
    after_vals = [comparison_dict['after_filter']['win_rate'], comparison_dict['after_filter']['avg_rr']]
    
    x = np.arange(len(labels))
    width = 0.35
    
    fig, ax = plt.subplots(figsize=(10, 6))
    rects1 = ax.bar(x - width/2, before_vals, width, label='Before Filter', color='grey')
    
    # Color After bar green if improved, red if declined
    after_colors = []
    if comparison_dict['win_rate_improvement'] >= 0:
        after_colors.append('green')
    else:
        after_colors.append('red')
        
    if comparison_dict['avg_rr_improvement'] >= 0:
        after_colors.append('green')
    else:
        after_colors.append('red')
        
    # Standard bar plot doesn't support list of colors for different bars in same call easily with grouped bars
    # So we plot them individually or use a loop
    rects2 = ax.bar(x + width/2, after_vals, width, label='After Filter', color='teal')
    
    ax.set_ylabel('Value')
    ax.set_title("Filtering Process Impact — Arjo's Argument System")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    
    plt.grid(axis='y', alpha=0.3)
    
    if save_path:
        plt.savefig(save_path)
        plt.close()
    else:
        plt.show()

def plot_argument_breakdown(ranking_list, save_path=None):
    """
    For each instrument: stacked bar showing bullish score vs bearish score.
    """
    if not ranking_list: return
    
    # Sort by score gap descending
    sorted_rankings = sorted(ranking_list, key=lambda x: x['score_gap'], reverse=True)
    
    instruments = [r['instrument'] for r in sorted_rankings]
    bull_scores = [r['bullish_score'] for r in sorted_rankings]
    bear_scores = [-r['bearish_score'] for r in sorted_rankings] # Negative for display
    
    plt.figure(figsize=(10, 6))
    plt.bar(instruments, bull_scores, color='green', label='Bullish Arguments')
    plt.bar(instruments, bear_scores, color='red', label='Bearish Arguments')
    
    plt.axhline(0, color='black', linewidth=0.8)
    plt.title("MMC Argument Scores by Instrument")
    plt.ylabel("Score")
    plt.legend()
    plt.grid(axis='y', alpha=0.3)
    
    if save_path:
        plt.savefig(save_path)
        plt.close()
    else:
        plt.show()

def plot_instrument_ranking(ranking_list, save_path=None):
    """
    Ranked list visualization.
    """
    if not ranking_list: return
    
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.axis('tight')
    ax.axis('off')
    
    columns = ['Rank', 'Instrument', 'Bias', 'Strength', 'Score Gap']
    data = []
    cell_colors = []
    
    color_map = {
        'HIGH': '#c6efce', # Light green
        'MEDIUM': '#ffeb9c', # Light amber
        'LOW': '#ffc7ce', # Light red
        'NEUTRAL': '#d9d9d9' # Grey
    }
    
    for r in ranking_list:
        data.append([
            r['rank'],
            r['instrument'],
            r['bias_direction'],
            r['bias_strength'],
            r['score_gap']
        ])
        
        row_color = color_map.get(r['bias_strength'], '#ffffff')
        cell_colors.append([row_color] * len(columns))
        
    table = ax.table(cellText=data, colLabels=columns, cellColours=cell_colors, loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.5)
    
    plt.title("Filtering Process — Instrument Rankings", pad=20)
    
    if save_path:
        plt.savefig(save_path)
        plt.close()
    else:
        plt.show()

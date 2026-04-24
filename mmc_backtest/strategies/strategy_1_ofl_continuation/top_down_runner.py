import pandas as pd
import numpy as np
import os
import time
from backtestv2 import load_data, run_s1_backtest, ForensicEngine, CONFIG, build_ai_dataset, train_institutional_filter

def get_htf_structural_bias(df_htf, instrument):
    engine = ForensicEngine(df_htf, instrument)
    it_points = engine.scan_it_points()
    it_points.sort(key=lambda x: x['index'])
    
    bias_series = np.full(len(df_htf), -1)
    target_series = np.full(len(df_htf), 0.0)
    
    it_idx = 0
    recent_it_high = None
    recent_it_low = None
    recent_type = None
    
    for i in range(len(df_htf)):
        while it_idx < len(it_points) and it_points[it_idx]['index'] <= i:
            it = it_points[it_idx]
            if it['type'] == 'IT_HIGH': 
                recent_it_high = it['level']
                recent_type = 'IT_HIGH'
            else: 
                recent_it_low = it['level']
                recent_type = 'IT_LOW'
            it_idx += 1
        
        if recent_type == 'IT_LOW':
            bias_series[i] = 1 
            target_series[i] = recent_it_high if recent_it_high else 0.0
        elif recent_type == 'IT_HIGH':
            bias_series[i] = 0
            target_series[i] = recent_it_low if recent_it_low else 0.0
            
    df_htf['bias'] = bias_series
    df_htf['htf_target'] = target_series
    return df_htf[['datetime', 'bias', 'htf_target']]

def run_top_down_analysis(ltf="5M", htf="1H", instrument="EURUSD", use_ai=True):
    TF_PERIODS = {"DAILY": "1440", "4H": "240", "1H": "60", "15M": "15", "5M": "5"}
    raw_path = r"c:\Users\Admin\OneDrive\Desktop\MMC\mmc_backtest\data\raw"
    
    try:
        ltf_file = f"{instrument}{TF_PERIODS[ltf]}.csv"
        htf_file = f"{instrument}{TF_PERIODS[htf]}.csv"
        df_ltf = load_data(os.path.join(raw_path, ltf_file))
        df_htf = load_data(os.path.join(raw_path, htf_file))
    except Exception as e:
        print(f"[!] Error loading {instrument} {ltf}/{htf}: {e}")
        return None
    
    bias_df = get_htf_structural_bias(df_htf, instrument)
    df_ltf = pd.merge_asof(df_ltf.sort_values('datetime'), bias_df.sort_values('datetime'), on='datetime', direction='backward')
    
    trades_td = run_s1_backtest(df_ltf, instrument, htf_bias=df_ltf['bias'].values, htf_erl=df_ltf['htf_target'].values)
    
    if not trades_td:
        return {"pair": f"{instrument} {ltf}/{htf}", "wr": 0, "rr": 0, "ai_wr": 0, "ai_rr": 0, "ai_trades": 0}
        
    ai_wr, ai_rr, ai_trades = 0, 0, 0
    rr_values = [t['rr_achieved'] for t in trades_td]
    wr = (sum(1 for r in rr_values if r > 0) / len(trades_td)) * 100

    if use_ai:
        from backtestv2 import train_institutional_filter, build_ai_dataset
        ai_df_raw = build_ai_dataset(df_ltf, trades_td)
        model, _, ai_df = train_institutional_filter(ai_df_raw)
        
        if model is not None and 'ai_win_prob' in ai_df.columns:
            threshold = ai_df['ai_win_prob'].quantile(0.80)
            ai_filtered = ai_df[ai_df['ai_win_prob'] >= threshold].copy()
            if len(ai_filtered) > 0:
                ai_wr = float(ai_filtered['win'].mean() * 100)
                ai_rr = float(ai_filtered['rr_achieved'].sum())
                ai_trades = int(len(ai_filtered))
                print(f"[AI REPORT] Pair: {instrument} {ltf}, MECH WR: {wr:.2f}%, AI WR: {ai_wr:.2f}%, AI TRADES: {ai_trades}")
    
    return {
        "pair": f"{instrument} {ltf}/{htf}",
        "wr": wr, "rr": sum(rr_values),
        "ai_wr": ai_wr, "ai_rr": ai_rr, "ai_trades": ai_trades
    }

def run_full_suite(instrument):
    pairs = [("1H", "DAILY"), ("15M", "4H"), ("5M", "1H")]
    res = []
    for ltf, htf in pairs:
        r = run_top_down_analysis(ltf, htf, instrument)
        if r: res.append(r)
    return res

if __name__ == "__main__":
    instruments = ["EURUSD", "GBPUSD", "XAUUSD"]
    all_res = []
    for inst in instruments:
        all_res.extend(run_full_suite(inst))
        
    print("\n" + "="*145)
    print("                      MMC INSTITUTIONAL AI PERFORMANCE REPORT (PURE PYTHON ENGINE)")
    print("="*145)
    print(f"{'INSTRUMENT/PAIR':<22} | {'MECH WR':<8} | {'MECH RR':<10} | {'AI WR':<8} | {'AI RR':<10} | {'AI TRADES':<10} | {'WR IMPROVE'}")
    print("-" * 145)
    for r in all_res:
        wr_improve = (r['ai_wr'] - r['wr']) if r['ai_wr'] > 0 else 0
        print(f"{r['pair']:<22} | {r['wr']:<8.2f}% | {r['rr']:<10.2f} | {r['ai_wr']:<8.2f}% | {r['ai_rr']:<10.2f} | {r['ai_trades']:<10} | {wr_improve:+.2f}%")
    print("="*145)

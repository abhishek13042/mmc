r"""
================================================================================
          MMC TRADING SYSTEM — MASTER BATCH RUNNER                           
          Runs ALL 7 Strategies x 3 Instruments x All Valid Timeframes       
          Saves results as CSV files to backtest/results/                    
                                                                             
   HOW TO RUN:                                                               
     cd c:\Users\Admin\OneDrive\Desktop\MMC                                  
     python mmc_backtest/run_all_strategies.py                               
                                                                             
   OUTPUT FILES:                                                             
     backtest/results/s1_ofl_EURUSD_H1.csv          <- one per run           
     backtest/results/s5_candle_EURUSD_D1_H1.csv    <- dual-TF runs          
     backtest/results/MASTER_SUMMARY.csv             <- all runs combined    
     backtest/results/BEST_PERFORMERS.csv            <- top run per strategy 
================================================================================
"""

import sys
import os
import csv
import json
import traceback
import importlib
import pandas as pd
from datetime import datetime
from pathlib import Path

THIS_FILE    = Path(__file__).resolve()
MMC_ROOT     = THIS_FILE.parent
PROJECT_ROOT = MMC_ROOT.parent

for p in [str(PROJECT_ROOT), str(MMC_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

DATA_DIR    = MMC_ROOT / 'data' / 'raw'
RESULTS_DIR = MMC_ROOT / 'backtest' / 'results'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

ALL_BATCH_RESULTS = []

INSTRUMENTS = ['EURUSD', 'GBPUSD', 'XAUUSD']

# Maps timeframe argument strings → actual filename suffix (minute-based naming)
# Files are named: {INSTRUMENT}{MINUTES}.csv
# e.g. EURUSD60.csv = 1H, EURUSD1440.csv = D1
TF_TO_FILE = {
    'DAILY'  : '1440',   # 1440 min = Daily
    '4H'     : '240',    # 240  min = 4 Hour
    '1H'     : '60',     # 60   min = 1 Hour
    '15M'    : '15',     # 15   min
    '5M'     : '5',      # 5    min
    '1M'     : '1',      # 1    min
    'WEEKLY' : '10080',  # 10080 min = Weekly (not available but mapped)
}

STRATEGY_REGISTRY = {
    1: {'name': 'OFL_CONTINUATION',  'short': 'ofl',       'module_path': 'strategies.strategy_1_ofl_continuation.backtest',      'fn_name': 'run_backtest', 'fn': None, 'import_ok': False, 'import_err': ''},
    2: {'name': 'FVA_IDEAL',         'short': 'fva_ideal', 'module_path': 'strategies.strategy_2_fva_ideal.backtest',              'fn_name': 'run_backtest', 'fn': None, 'import_ok': False, 'import_err': ''},
    3: {'name': 'FVA_GOOD',          'short': 'fva_good',  'module_path': 'strategies.strategy_3_fva_good.backtest',               'fn_name': 'run_backtest', 'fn': None, 'import_ok': False, 'import_err': ''},
    4: {'name': 'SWEEP_OFL',         'short': 'sweep',     'module_path': 'strategies.strategy_4_sweep_ofl.backtest',              'fn_name': 'run_backtest', 'fn': None, 'import_ok': False, 'import_err': ''},
    5: {'name': 'CANDLE_SCIENCE',    'short': 'candle',    'module_path': 'strategies.strategy_5_candle_science.backtest',         'fn_name': 'run_backtest', 'fn': None, 'import_ok': False, 'import_err': ''},
    6: {'name': 'SHARP_TURN',        'short': 'sharp',     'module_path': 'strategies.strategy_6_sharp_turn.backtest',             'fn_name': 'run_backtest', 'fn': None, 'import_ok': False, 'import_err': ''},
    7: {'name': 'ORDER_FLOW_ENTRY',  'short': 'oflow',     'module_path': 'strategies.strategy_7_order_flow_entry.backtest',       'fn_name': 'run_backtest', 'fn': None, 'import_ok': False, 'import_err': ''},
    8: {'name': 'IT_RETRACEMENT',    'short': 'itretrace', 'module_path': 'strategies.strategy_8_it_retracement.backtest',         'fn_name': 'run_backtest', 'fn': None, 'import_ok': False, 'import_err': ''},
    9: {'name': 'PCH_PCL_SWEEP',     'short': 'pchsweep',  'module_path': 'strategies.strategy_9_pch_pcl_sweep.backtest',          'fn_name': 'run_backtest', 'fn': None, 'import_ok': False, 'import_err': ''},
}

def import_all_strategies():
    print("\n" + "="*70)
    print("IMPORTING STRATEGY MODULES")
    print("="*70)
    for num, reg in STRATEGY_REGISTRY.items():
        try:
            mod = importlib.import_module(reg['module_path'])
            reg['fn'] = getattr(mod, reg['fn_name'])
            reg['import_ok'] = True
            print(f"  [OK]   S{num} — {reg['name']}")
        except Exception as e:
            reg['import_err'] = str(e)
            print(f"  [FAIL] S{num} — {reg['name']}: {e}")

def data_file_exists(instrument: str, tf_string: str) -> tuple[bool, str]:
    """
    Check if the CSV file exists for a given instrument + timeframe string.
    tf_string can be 'DAILY', '4H', '1H', '15M', '5M' etc.

    Actual filename format: {INSTRUMENT}{MINUTES}.csv
    Examples:
      EURUSD + 'DAILY' → EURUSD1440.csv
      GBPUSD + '4H'    → GBPUSD240.csv
      XAUUSD + '1H'    → XAUUSD60.csv
      EURUSD + '15M'   → EURUSD15.csv
      GBPUSD + '5M'    → GBPUSD5.csv

    Returns (exists: bool, filepath: str)
    """
    minutes  = TF_TO_FILE.get(tf_string, tf_string)
    filepath = DATA_DIR / f'{instrument}{minutes}.csv'
    return filepath.exists(), str(filepath)

def verify_all_data():
    print("\n" + "="*70)
    print("VERIFYING DATA FILES")
    print("  Format: {INSTRUMENT}{MINUTES}.csv  e.g. EURUSD60.csv = 1H")
    print("="*70)
    all_tf = ['DAILY', '4H', '1H', '15M', '5M']
    tf_display = {
        'DAILY': 'D1   (1440min)',
        '4H'  : 'H4   (240min)',
        '1H'  : 'H1   (60min)',
        '15M' : 'M15  (15min)',
        '5M'  : 'M5   (5min)',
    }
    missing = []
    print(f"  Checking for 15 required data files...")
    for inst in INSTRUMENTS:
        print(f"\n  {inst}:")
        for tf in all_tf:
            ok, path = data_file_exists(inst, tf)
            status = 'OK     ' if ok else 'MISSING'
            if not ok:
                missing.append(path)
            fname = os.path.basename(path)
            label = tf_display.get(tf, tf)
            print(f"    [{status}] {fname:<20} ({label})")
    if missing:
        print(f"\n  WARNING: {len(missing)} data file(s) missing.")
        print("  Those combinations will be SKIPPED during the run.")
    else:
        print("\n  All data files present.")

SUMMARY_CSV_COLUMNS = [
    'run_timestamp', 'strategy_num', 'strategy', 'instrument', 'timeframe',
    'run_label', 'status', 'total_signals', 'wins', 'losses', 'neutrals',
    'win_rate_pct', 'avg_rr', 'total_rr', 'max_consecutive_losses',
    'best_trade_rr', 'worst_trade_rr', 'output_csv', 'error_message',
]

TRADE_CSV_COLUMNS = [
    'run_label', 'strategy', 'instrument', 'timeframe', 'signal_datetime',
    'direction', 'entry_price', 'stop_loss', 'tp_2r', 'tp_4r', 'risk_pips',
    'result', 'rr_achieved', 'exit_datetime', 'pfvg_high', 'pfvg_low',
    'ofl_probability', 'ofl_swing_price', 'fva_high', 'fva_low',
    'fvg_in_high', 'fvg_in_low', 'fvg_out_high', 'fvg_out_low',
    'candles_to_form_fvg_out', 'context_target', 'ofl_1_swing', 'ofl_2_swing',
    'checklist_passed', 'conditions_met',
]

MASTER_SUMMARY_PATH = RESULTS_DIR / 'MASTER_SUMMARY.csv'
all_summary_rows    = []

def safe(val, default=''):
    if val is None: return default
    if isinstance(val, list): return '|'.join(str(v) for v in val)
    if isinstance(val, dict): return str(val)
    if isinstance(val, float): return f'{val:.5f}'
    return str(val)

def trades_to_csv(trades, run_label, strategy, instrument, timeframe, output_path):
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=TRADE_CSV_COLUMNS, extrasaction='ignore')
        writer.writeheader()
        for trade in trades:
            row = {col: safe(trade.get(col, '')) for col in TRADE_CSV_COLUMNS}
            row['run_label'] = run_label
            row['strategy']  = strategy
            row['instrument']= instrument
            row['timeframe'] = timeframe
            writer.writerow(row)

def append_to_master_summary(row_dict):
    file_exists = MASTER_SUMMARY_PATH.exists()
    rows = []
    if file_exists:
        with open(MASTER_SUMMARY_PATH, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    
    # DEDUP: strategy + instrument + timeframe
    new_rows = []
    found = False
    for r in rows:
        if r['strategy'] == row_dict['strategy'] and \
           r['instrument'] == row_dict['instrument'] and \
           r['timeframe'] == row_dict['timeframe']:
            new_rows.append(row_dict)
            found = True
        else:
            new_rows.append(r)
    
    if not found:
        new_rows.append(row_dict)
    
    with open(MASTER_SUMMARY_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_CSV_COLUMNS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(new_rows)

def _build_summary_row(strategy_num, strategy_name, instrument, timeframe,
    label, status, output_csv_name, total_signals=0, wins=0, losses=0,
    neutrals=0, win_rate_pct=0.0, avg_rr=0.0, total_rr=0.0,
    max_consecutive_losses=0, best_trade_rr=0.0, worst_trade_rr=0.0, error=''):
    return {
        'run_timestamp': datetime.now().isoformat(), 'strategy_num': strategy_num,
        'strategy': strategy_name, 'instrument': instrument, 'timeframe': timeframe,
        'run_label': label, 'status': status, 'total_signals': total_signals,
        'wins': wins, 'losses': losses, 'neutrals': neutrals,
        'win_rate_pct': f'{win_rate_pct:.2f}', 'avg_rr': f'{avg_rr:.3f}',
        'total_rr': f'{total_rr:.3f}', 'max_consecutive_losses': max_consecutive_losses,
        'best_trade_rr': f'{best_trade_rr:.2f}', 'worst_trade_rr': f'{worst_trade_rr:.2f}',
        'output_csv': output_csv_name, 'error_message': error,
    }

def run_one(strategy_num, label, instrument, timeframe_label, output_csv_name, call_kwargs):
    reg         = STRATEGY_REGISTRY[strategy_num]
    output_path = RESULTS_DIR / output_csv_name
    
    # --- SKIP LOGIC: If already 'OK' in MASTER_SUMMARY, skip ---
    if MASTER_SUMMARY_PATH.exists():
        try:
            summary_df = pd.read_csv(MASTER_SUMMARY_PATH)
            # Find if this specific run is already 'OK'
            existing = summary_df[
                (summary_df['strategy'] == reg['name']) & 
                (summary_df['instrument'] == instrument) & 
                (summary_df['timeframe'] == timeframe_label) & 
                (summary_df['status'] == 'OK')
            ]
            if not existing.empty:
                print(f"  [ALREADY DONE] {label}")
                # Load stats from existing row for report
                row = existing.iloc[0].to_dict()
                all_summary_rows.append(row)
                return
        except:
            pass

    print(f"\n  > {label}")

    if not reg['import_ok']:
        msg = f"Import failed: {reg['import_err']}"
        print(f"    [SKIP] {msg}")
        row = _build_summary_row(strategy_num, reg['name'], instrument, timeframe_label, label, 'SKIPPED', output_csv_name, error=msg)
        append_to_master_summary(row)
        all_summary_rows.append(row)
        return

    result = None
    try:
        result = reg['fn'](data_dir=str(DATA_DIR), **call_kwargs)
        if result is None:
            print("    [ERROR] No result returned from backtest function")
            return

        # Handle both flat results and nested 'stats' results
        if isinstance(result, dict) and 'stats' in result:
            result.update(result.pop('stats'))
            
        total    = result.get('total_signals', 0)
        wins     = result.get('wins', 0)
        losses   = result.get('losses', 0)
        neutrals = result.get('neutrals', 0)
        wr       = result.get('win_rate_pct', 0.0)
        avg_rr   = result.get('avg_rr', 0.0)
        tot_rr   = result.get('total_rr', 0.0)
        trades   = result.get('trades', [])

        print(f"    [OK] Signals:{total} | Wins:{wins} | Losses:{losses} | WR:{wr:.1f}% | AvgRR:{avg_rr:.2f}")
        trades_to_csv(trades, label, reg['name'], instrument, timeframe_label, output_path)
        print(f"    [SAVED] {output_csv_name}")

        row = _build_summary_row(strategy_num, reg['name'], instrument, timeframe_label,
            label, 'OK', output_csv_name, total_signals=total, wins=wins, losses=losses,
            neutrals=neutrals, win_rate_pct=wr, avg_rr=avg_rr, total_rr=tot_rr)
    except Exception as e:
        tb  = traceback.format_exc()
        msg = str(e)
        print(f"    [ERROR] {msg}")
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerows([['error', 'traceback'], [msg, tb]])
        row = _build_summary_row(strategy_num, reg['name'], instrument, timeframe_label, label, 'ERROR', output_csv_name, error=msg)

    append_to_master_summary(row)
    all_summary_rows.append(row)
    if result is not None:
        ALL_BATCH_RESULTS.append(result)

def _skip(num, name, inst, tf_label, label, out_name, path):
    print(f"\n  > {label}")
    print(f"    [SKIP] Missing: {path}")
    row = _build_summary_row(num, name, inst, tf_label, label, 'SKIPPED', out_name, error=f'missing {path}')
    append_to_master_summary(row)
    all_summary_rows.append(row)

def run_strategy_1():
    print("\n" + "="*70); print("STRATEGY 1 — OFL Continuation  [9 runs]"); print("="*70)
    for tf_arg, tf_f in [('4H','H4'),('1H','H1'),('15M','M15')]:
        for inst in INSTRUMENTS:
            ok, path = data_file_exists(inst, tf_arg)
            label, out = f"S1 | {inst} | {tf_f}", f"s1_ofl_{inst}_{tf_f}.csv"
            if not ok: _skip(1,'OFL_CONTINUATION',inst,tf_f,label,out,path); continue
            run_one(1, label, inst, tf_f, out, {'instrument': inst, 'timeframe': tf_arg})

def run_strategy_2():
    print("\n" + "="*70); print("STRATEGY 2 — FVA Ideal  [9 runs]"); print("="*70)
    for tf_arg, tf_f in [('4H','H4'),('1H','H1'),('15M','M15')]:
        for inst in INSTRUMENTS:
            ok, path = data_file_exists(inst, tf_arg)
            label, out = f"S2 | {inst} | {tf_f}", f"s2_fva_ideal_{inst}_{tf_f}.csv"
            if not ok: _skip(2,'FVA_IDEAL',inst,tf_f,label,out,path); continue
            run_one(2, label, inst, tf_f, out, {'instrument': inst, 'timeframe': tf_arg})

def run_strategy_3():
    print("\n" + "="*70); print("STRATEGY 3 — FVA Good  [9 runs]"); print("="*70)
    for tf_arg, tf_f in [('4H','H4'),('1H','H1'),('15M','M15')]:
        for inst in INSTRUMENTS:
            ok, path = data_file_exists(inst, tf_arg)
            label, out = f"S3 | {inst} | {tf_f}", f"s3_fva_good_{inst}_{tf_f}.csv"
            if not ok: _skip(3,'FVA_GOOD',inst,tf_f,label,out,path); continue
            run_one(3, label, inst, tf_f, out, {'instrument': inst, 'timeframe': tf_arg})

def run_strategy_4():
    print("\n" + "="*70); print("STRATEGY 4 — Sweep + OFL  [9 runs]"); print("="*70)
    for tf_arg, tf_f in [('1H','H1'),('15M','M15'),('5M','M5')]:
        for inst in INSTRUMENTS:
            ok, path = data_file_exists(inst, tf_arg)
            label, out = f"S4 | {inst} | {tf_f}", f"s4_sweep_{inst}_{tf_f}.csv"
            if not ok: _skip(4,'SWEEP_OFL',inst,tf_f,label,out,path); continue
            run_one(4, label, inst, tf_f, out, {'instrument': inst, 'timeframe': tf_arg})

def run_strategy_5():
    print("\n" + "="*70); print("STRATEGY 5 — Candle Science  [9 runs]"); print("="*70)
    for htf_arg, ltf_arg, hf, lf in [('DAILY','1H','D1','H1'),('4H','15M','H4','M15'),('1H','5M','H1','M5')]:
        for inst in INSTRUMENTS:
            ok_h, ph = data_file_exists(inst, htf_arg)
            ok_l, pl = data_file_exists(inst, ltf_arg)
            tf_label = f"{hf}->{lf}"; label = f"S5 | {inst} | {tf_label}"; out = f"s5_candle_{inst}_{hf}_{lf}.csv"
            if not ok_h or not ok_l: _skip(5,'CANDLE_SCIENCE',inst,tf_label,label,out,ph if not ok_h else pl); continue
            run_one(5, label, inst, tf_label, out, {'instrument': inst, 'htf': htf_arg, 'ltf': ltf_arg})

def run_strategy_6():
    print("\n" + "="*70); print("STRATEGY 6 — Sharp Turn  [15 runs]"); print("="*70)
    for ctx_arg, ent_arg, cf, ef in [('DAILY','1H','D1','H1'),('4H','15M','H4','M15'),('4H','1H','H4','H1'),('1H','15M','H1','M15'),('1H','5M','H1','M5')]:
        for inst in INSTRUMENTS:
            ok_c, pc = data_file_exists(inst, ctx_arg)
            ok_e, pe = data_file_exists(inst, ent_arg)
            tf_label = f"{cf}->{ef}"; label = f"S6 | {inst} | {tf_label}"; out = f"s6_sharp_{inst}_{cf}_{ef}.csv"
            if not ok_c or not ok_e: _skip(6,'SHARP_TURN',inst,tf_label,label,out,pc if not ok_c else pe); continue
            run_one(6, label, inst, tf_label, out, {'instrument': inst, 'context_tf': ctx_arg, 'entry_tf': ent_arg})

def run_strategy_7():
    print("\n" + "="*70); print("STRATEGY 7 — Order Flow Entry  [15 runs]"); print("="*70)
    for ctx_arg, ent_arg, cf, ef in [('DAILY','15M','D1','M15'),('4H','15M','H4','M15'),('4H','1H','H4','H1'),('1H','5M','H1','M5'),('1H','15M','H1','M15')]:
        for inst in INSTRUMENTS:
            ok_c, pc = data_file_exists(inst, ctx_arg)
            ok_e, pe = data_file_exists(inst, ent_arg)
            tf_label = f"{cf}->{ef}"; label = f"S7 | {inst} | {tf_label}"; out = f"s7_oflow_{inst}_{cf}_{ef}.csv"
            if not ok_c or not ok_e: _skip(7,'ORDER_FLOW_ENTRY',inst,tf_label,label,out,pc if not ok_c else pe); continue
            run_one(7, label, inst, tf_label, out, {'instrument': inst, 'context_tf': ctx_arg, 'entry_tf': ent_arg})

def run_strategy_8():
    print("\n" + "="*70); print("STRATEGY 8 — IT Retracement  [9 runs]"); print("="*70)
    for tf_arg, tf_f in [('4H','H4'),('1H','H1'),('15M','M15')]:
        for inst in INSTRUMENTS:
            ok, path = data_file_exists(inst, tf_arg)
            label, out = f"S8 | {inst} | {tf_f}", f"s8_itretrace_{inst}_{tf_f}.csv"
            if not ok: _skip(8,'IT_RETRACEMENT',inst,tf_f,label,out,path); continue
            run_one(8, label, inst, tf_f, out, {'instrument': inst, 'timeframe': tf_arg})

def run_strategy_9():
    print("\n" + "="*70); print("STRATEGY 9 — PCH/PCL Sweep  [9 runs]"); print("="*70)
    for tf_arg, tf_f in [('1H','H1'),('15M','M15'),('5M','M5')]:
        for inst in INSTRUMENTS:
            ok, path = data_file_exists(inst, tf_arg)
            label, out = f"S9 | {inst} | {tf_f}", f"s9_pchsweep_{inst}_{tf_f}.csv"
            if not ok: _skip(9,'PCH_PCL_SWEEP',inst,tf_f,label,out,path); continue
            run_one(9, label, inst, tf_f, out, {'instrument': inst, 'timeframe': tf_arg})

def write_best_performers():
    best = {}
    for row in all_summary_rows:
        if row['status'] != 'OK': continue
        try: wr = float(row['win_rate_pct'])
        except: continue
        s = row['strategy']
        if s not in best or wr > float(best[s]['win_rate_pct']):
            best[s] = row
    out_path = RESULTS_DIR / 'BEST_PERFORMERS.csv'
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_CSV_COLUMNS, extrasaction='ignore')
        writer.writeheader()
        for row in best.values(): writer.writerow(row)
    return best

def run_strategy_10():
    """
    Apply the Filtering Process to all signals collected
    from S1-S9 in this batch run.
    """
    from mmc_backtest.strategies.strategy_10_filtering_process import argument_scorer, filter_overlay, backtest as s10
    import pandas as pd
    
    print("\n" + "="*70)
    print("STRATEGY 10 — FILTERING PROCESS ANALYSIS")
    print("="*70)

    # Step 1: Score and rank all instruments
    rankings = argument_scorer.rank_instruments(INSTRUMENTS, str(DATA_DIR))
    print("\nINSTRUMENT RANKINGS:")
    for r in rankings:
        print(f"  #{r['rank']} {r['instrument']}: {r['bias_direction']} ({r['bias_strength']}) | Bull={r['bullish_score']} Bear={r['bearish_score']}")
        print(f"     → {r['recommendation']}")

    # Step 2: Collect ALL signals from ALL strategies this run
    all_signals = []
    for result in ALL_BATCH_RESULTS:
        if isinstance(result, dict) and 'trades' in result:
            all_signals.extend(result['trades'])

    if not all_signals:
        print("\n[WARNING] No signals found to filter. Run S1-S9 first.")
        return

    # Step 3: Apply filter
    filter_result = filter_overlay.apply_filter_to_signals(all_signals, str(DATA_DIR))

    print(f"\nFILTER RESULT:")
    print(f"  Total signals: {filter_result['filter_stats']['total_signals']}")
    print(f"  Accepted:      {filter_result['filter_stats']['accepted_count']}")
    print(f"  Rejected:      {filter_result['filter_stats']['rejected_count']}")
    print(f"  Acceptance Rate: {filter_result['filter_stats']['acceptance_rate_pct']}%")

    # Step 4: Compare before vs after
    comparison = s10.run_comparison_backtest(all_signals, filter_result['accepted'])

    # Step 5: Save rankings to CSV
    rankings_df = pd.DataFrame(rankings)
    rankings_df.to_csv(RESULTS_DIR / 'FILTERING_PROCESS_RANKINGS.csv', index=False)

    # Step 6: Save comparison to CSV
    comp_df = pd.DataFrame([comparison])
    comp_df.to_csv(RESULTS_DIR / 'FILTERING_PROCESS_COMPARISON.csv', index=False)

    print(f"\n[SAVED] {RESULTS_DIR / 'FILTERING_PROCESS_RANKINGS.csv'}")
    print(f"[SAVED] {RESULTS_DIR / 'FILTERING_PROCESS_COMPARISON.csv'}")

def print_final_summary(best):
    total  = len(all_summary_rows)
    ok     = sum(1 for r in all_summary_rows if r['status'] == 'OK')
    errors = sum(1 for r in all_summary_rows if r['status'] == 'ERROR')
    skips  = sum(1 for r in all_summary_rows if r['status'] == 'SKIPPED')

    print("\n\n" + "="*95)
    print("MASTER RESULTS SUMMARY")
    print("="*95)
    print(f"  {'#':<3} {'Label':<40} {'Signals':>8} {'Wins':>6} {'Losses':>7} {'WR%':>7} {'Status':>9}")
    print("-"*95)
    for i, r in enumerate(all_summary_rows, 1):
        print(f"  {i:<3} {r['run_label']:<40} {str(r['total_signals']):>8} {str(r['wins']):>6} {str(r['losses']):>7} {str(r['win_rate_pct']):>7} {r['status']:>9}")
    print("="*95)
    print(f"  Total:{total} | OK:{ok} | Errors:{errors} | Skipped:{skips}")
    print("\n-- BEST PERFORMING RUN PER STRATEGY --")
    for s, row in best.items():
        print(f"  {s:<25} {row['run_label']:<40} WR:{row['win_rate_pct']}% AvgRR:{row['avg_rr']}")
    print(f"\n  MASTER_SUMMARY : {MASTER_SUMMARY_PATH}")
    print(f"  BEST_PERFORMERS: {RESULTS_DIR / 'BEST_PERFORMERS.csv'}")
    print("\n" + "="*95)
    print("  BATCH COMPLETE.")
    print("="*95 + "\n")

if __name__ == '__main__':
    start = datetime.now()
    print("="*70)
    print("  MMC TRADING SYSTEM — MASTER BATCH RUNNER")
    print(f"  Started: {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Root   : {MMC_ROOT}")
    print("="*70)

    # Master Summary persistence with dedup handled in append_to_master_summary
    # if MASTER_SUMMARY_PATH.exists():
    #     MASTER_SUMMARY_PATH.unlink()

    import_all_strategies()
    verify_all_data()

    run_strategy_1()
    run_strategy_2()
    run_strategy_3()
    run_strategy_4()
    run_strategy_5()
    run_strategy_6()
    run_strategy_7()
    run_strategy_8()
    run_strategy_9()

    best    = write_best_performers()
    
    # Run Filtering Process (Strategy 10)
    try:
        run_strategy_10()
    except Exception as e:
        print(f"\n[ERROR] Strategy 10 failed: {e}")
        traceback.print_exc()

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n  Total runtime: {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print_final_summary(best)

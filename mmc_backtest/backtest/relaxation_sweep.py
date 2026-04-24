import os
import json
import subprocess
import pandas as pd
from datetime import datetime

# Paths
BASE_DIR = r"c:\Users\Admin\OneDrive\Desktop\MMC\mmc_backtest"

STRATEGIES = {
    "strategy_1_ofl_continuation": {
        "script": "strategies/strategy_1_ofl_continuation/backtest.py",
        "args": ["--instrument", "EURUSD", "--timeframe", "DAILY"],
        "relaxed": {
            "parameters": {
                "ofl_probability_labels": ["HIGH", "MEDIUM", "LOW"],
                "fvg_types_allowed": ["PFVG", "BFVG"],
                "check_opposing_pda": False
            }
        }
    },
    "strategy_2_fva_ideal": {
        "script": "strategies/strategy_2_fva_ideal/backtest.py",
        "args": ["--instrument", "EURUSD", "--timeframe", "4H"],
        "relaxed": {
            "parameters": {
                "fva_types_allowed": ["IDEAL", "GOOD"],
                "check_ofl_confluence": False
            }
        }
    },
    "strategy_3_liquidity_sweep": {
        "script": "strategies/strategy_3_liquidity_sweep/backtest.py",
        "args": ["--instrument", "EURUSD", "--timeframe", "1H"],
        "relaxed": {
            "parameters": {
                "sweep_types_allowed": ["SWEEP", "RUN"],
                "min_wick_ratio": 0.3
            }
        }
    },
    "strategy_5_candle_science": {
        "script": "strategies/strategy_5_candle_science/backtest.py",
        "args": ["--instrument", "EURUSD", "--htf", "DAILY", "--ltf", "1H"],
        "relaxed": {
            "parameters": {
                "min_confidence_score": 40,
                "fvg_types_allowed": ["PFVG", "BFVG"]
            }
        }
    },
    "strategy_6_sharp_turn": {
        "script": "strategies/strategy_6_sharp_turn/backtest.py",
        "args": ["--instrument", "EURUSD", "--ctx", "DAILY", "--ent", "1H"],
        "relaxed": {
            "parameters": {
                "fvg_types_allowed": ["PFVG", "BFVG", "RFVG"],
                "max_reversal_candles": 5
            }
        }
    },
    "strategy_7_order_flow_entry": {
        "script": "strategies/strategy_7_order_flow_entry/backtest.py",
        "args": ["--instrument", "EURUSD", "--ctx", "DAILY", "--ent", "15M"],
        "relaxed": {
            "parameters": {
                "min_checklist_pass": 4,
                "fvg_types_allowed": ["PFVG", "BFVG", "RFVG"]
            }
        }
    }
}

def update_config(strategy_dir, config_data):
    config_path = os.path.join(BASE_DIR, "strategies", strategy_dir, "config.json")
    if not os.path.exists(config_path):
        print(f"Warning: Config not found at {config_path}")
        return
        
    with open(config_path, 'r') as f:
        full_config = json.load(f)
    
    # Track "current" before update
    previous = full_config.get('parameters', {}).copy()
    
    # Update parameters
    full_config['parameters'].update(config_data['parameters'])
    
    # Log the change
    history_entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "previous": previous,
        "new": full_config['parameters'],
        "mode": "Relaxed"
    }
    if 'history' not in full_config: full_config['history'] = []
    full_config['history'].append(history_entry)
    
    with open(config_path, 'w') as f:
        json.dump(full_config, f, indent=2)

def run_strategy_backtest(strategy_name, config):
    print(f"\n>>> Running {strategy_name} (Relaxed)...")
    update_config(strategy_name, config['relaxed'])
    
    cmd = ["python", config['script']] + config['args']
    print(f"Executing: {' '.join(cmd)}")
    # We use os.system for direct progress visibility if possible, or just print output
    try:
        # Run and print output as it happens
        process = subprocess.Popen(cmd, cwd=BASE_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            print(line, end="")
        process.wait()
        return process.returncode == 0
    except Exception as e:
        print(f"Error executing {strategy_name}: {e}")
        return False

def main():
    sweep_results = []
    for name, config in STRATEGIES.items():
        success = run_strategy_backtest(name, config)
        if success: sweep_results.append(name)
            
    print("\n--- Relaxation Sweep Complete ---")
    print(f"Successfully swept: {', '.join(sweep_results)}")

if __name__ == "__main__":
    main()

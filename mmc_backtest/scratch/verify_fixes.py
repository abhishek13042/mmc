import sys
import os
from pathlib import Path

# Add project root and mmc_backtest folder to path
MMC_ROOT = Path(r'C:\Users\Admin\OneDrive\Desktop\MMC\mmc_backtest')
PROJECT_ROOT = MMC_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(MMC_ROOT))

print("Checking Strategy Scanner Imports...")
strategies = [
    'strategies.strategy_1_ofl_continuation.scanner',
    'strategies.strategy_2_fva_ideal.scanner',
    'strategies.strategy_3_fva_good.scanner',
    'strategies.strategy_4_sweep_ofl.scanner',
    'strategies.strategy_5_candle_science.scanner',
    'strategies.strategy_6_sharp_turn.scanner',
    'strategies.strategy_7_order_flow_entry.scanner'
]

for s in strategies:
    try:
        __import__(s)
        print(f"  [OK] {s}")
    except Exception as e:
        print(f"  [FAIL] {s}: {e}")

print("\nVerifying Data Files via Master Runner...")
# We can't easily run just the verify part without triggering everything unless we import it
try:
    from mmc_backtest.run_all_strategies import verify_all_data
    verify_all_data()
except Exception as e:
    print(f"  [FAIL] verify_all_data: {e}")

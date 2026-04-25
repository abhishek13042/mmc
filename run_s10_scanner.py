import sys, os
from pathlib import Path

# Fix paths
THIS_FILE = Path(__file__).resolve()
MMC_ROOT = THIS_FILE.parent / 'mmc_backtest'
PROJECT_ROOT = THIS_FILE.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(MMC_ROOT))

from mmc_backtest.strategies.strategy_10_filtering_process.argument_scorer import rank_instruments

INSTRUMENTS = ['EURUSD', 'GBPUSD', 'XAUUSD']
DATA_DIR = MMC_ROOT / 'data' / 'raw'

def main():
    print("\n" + "="*70)
    print("   MMC STRATEGY 10 — TOP-DOWN ARGUMENT SCANNER")
    print("   Source: Arjo Video 12 (Filtering Process)")
    print("="*70)

    # Run the scorer on all instruments
    rankings = rank_instruments(INSTRUMENTS, str(DATA_DIR))

    print(f"\n{'RANK':<5} {'INSTRUMENT':<12} {'BIAS':<10} {'STRENGTH':<10} {'BULL/BEAR GAP'}")
    print("-" * 70)
    
    for r in rankings:
        print(f"#{r['rank']:<4} {r['instrument']:<12} {r['bias_direction']:<10} {r['bias_strength']:<10} {r['bullish_score']} vs {r['bearish_score']}")
        print(f"      RECO: {r['recommendation']}")
        print(f"      ARGS BULL: {', '.join(r['arguments_bullish'][:3])}...")
        print(f"      ARGS BEAR: {', '.join(r['arguments_bearish'][:3])}...")
        print("-" * 70)

    print("\n[COMPLETE] Use the HIGH strength instruments for your S1-S9 trading today.")

if __name__ == '__main__':
    main()

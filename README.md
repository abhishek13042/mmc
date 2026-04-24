# MMC Backtesting System

An institutional-grade trading simulation engine for validating MMC (Market Maker Cycles) strategies.

## Overview
This system provides a mechanical framework to backtest and analyze the "Big 7" MMC strategies. It is built to handle multi-timeframe alignment, institutional checklist validation, and high-volume batch processing across multiple currency pairs and commodities.

## Core Strategies
1. **S1: OFL Continuation** — Tracking order flow momentum.
2. **S2: FVA Ideal** — Premium value area entries.
3. **S3: FVA Good** — Standard value area entries.
4. **S4: Sweep + OFL** — Liquidity sweeps with order flow confirmation.
5. **S5: Candle Science** — High-probability candle patterns and structural shifts.
6. **S6: Sharp Turn** — Rapid reaction entries at context boundaries.
7. **S7: Order Flow Entry** — The most rigorous setup requiring dual OFL confirmation and a 10-point checklist.

## Getting Started

### 1. Prerequisites
- Python 3.9 or higher.
- Git (for version control).

### 2. Installation
Clone the repository (if not already local) and install dependencies:
```powershell
# Create and activate virtual environment (optional but recommended)
python -m venv venv
.\venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

### 3. Data Setup
The system expects MT5-exported CSV files in:
`mmc_backtest/data/raw/`

**Naming Convention:** `{INSTRUMENT}{TF_MINUTES}.csv`
- EURUSD1440.csv (Daily)
- EURUSD60.csv (1H)
- EURUSD15.csv (15M)

### 4. Running Backtests

**Run all strategies at once:**
```powershell
python mmc_backtest/run_all_strategies.py
```

**Run a specific strategy:**
```powershell
# Example: Run Strategy 6 Sharp Turn
python mmc_backtest/strategies/strategy_6_sharp_turn/backtest.py
```

## Reporting & Analytics
After running a backtest, check the `mmc_backtest/backtest/results/` folder:
- **Individual CSVs**: Every trade signal with its entry, stop loss, and RR outcome.
- **MASTER_SUMMARY.csv**: Comparative stats across all instruments and timeframes.
- **BEST_PERFORMERS.csv**: Automatically identifies the most profitable configurations.

## Contributing
Please ensure all new strategies follow the module structure: `__init__.py`, `scanner.py`, `backtest.py`, and `visualize.py`.

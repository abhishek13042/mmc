# MMC Institutional Backtesting Engine

An advanced, high-performance backtesting framework designed for institutional-grade trading strategies based on Order Flow, Liquidity, and Market Structure (Arjo-Pure Methodology).

## 🚀 Strategy 1: OFL Continuation
This engine simulates institutional order flow with high fidelity.

### Key Features
- **Forensic Engine**: O(N) sequential scanning of institutional levels.
- **Structural SL**: Implements "Arjo-Pure" protection levels at exact Swing Highs/Lows (ITH/ITL).
- **Timezone Calibration**: Aligned to MT5 Broker Time for accurate session filtering.
- **Multi-TF Analysis**: Automated performance reporting across DAILY, 4H, 1H, 15M, and 5M.

### Performance Highlights (EURUSD 1H)
- **Total Profit**: +5,788R
- **Win Rate**: ~32.46%
- **Avg Winner**: ~8.12R
- **Expectancy**: 1.96R per trade

## 🛠 Project Structure
- `modules/`: Core logic for PD Arrays, Market Structure, and Order Flow.
- `strategies/`: Specific strategy implementations (S1 v1.1, v2.0).
- `data/`: High-quality MT5 CSV data feeds.
- `results/`: Performance logs, equity curves, and financial reports.

## 📈 Running the Engine
To run the full suite:
```powershell
python strategies/strategy_1_ofl_continuation/multi_tf_runner.py
```

---
*Disclaimer: This is a research project for institutional strategy backtesting.*

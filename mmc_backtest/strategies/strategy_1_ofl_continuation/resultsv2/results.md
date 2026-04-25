# Strategy 1: OFL Continuation — Full Performance Report (v2)

This report contains the results of Strategy 1 after applying the **Critical Institutional Fixes** (Structural Stop Loss, Full History Scan) based on Arjo's Video 11 and 12.

## 📊 Performance Summary (Full History)

| Instrument | Timeframe | Signals | Win Rate | Avg RR | Total RR | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **EURUSD** | **H4** | 770 | 29.43% | 2.17 | +1668.5 | ✅ OK |
| **GBPUSD** | **H4** | 768 | 31.90% | 2.50 | +1917.1 | ✅ OK |
| **XAUUSD** | **H4** | 814 | 34.40% | 2.90 | +2364.4 | ✅ OK |
| **EURUSD** | **H1** | 2,948 | 32.46% | 1.96 | +5788.7 | ✅ OK |
| **GBPUSD** | **H1** | 2,909 | 30.90% | 1.83 | +5325.2 | ✅ OK |
| **XAUUSD** | **H1** | 3,108 | 31.70% | 2.29 | +7129.9 | ✅ OK |
| **EURUSD** | **M15** | 2,826 | 32.41% | 1.19 | +3349.2 | ✅ OK |

## 🛠️ Logic & Rules (Institutional Update)

### 1. The Entry Model
- **Setup**: Price breaks a swing point, creating an **Order Flow Leg (OFL)**.
- **Trigger**: Price retraces into a **Fair Value Gap (FVG)** that resides within the Discount/Premium zone of that specific OFL.
- **Direction**: Must align with the current OFL direction (Bullish/Bearish).

### 2. The Stop Loss Rule (Arjo's Exact Rule)
> "Stop loss above the most recent order flow lag in a bearish situation. A bullish situation, stop loss below the most recent order flow lag as well."

- **Rule**: The Stop Loss is placed **exactly** at the swing point price of the most recent OFL.
- **Fix**: Removed all previous pip buffers (0.0000x offsets) to ensure purely structural protection.

### 3. Take Profit
- **Primary**: Exit at the opposing External Range Liquidity (ERL) — usually the recent IT High or IT Low.
- **Secondary**: Minimum 2R requirement for trade acceptance.

## 📁 Files Included in this Folder
- `s1_ofl_*.csv`: Detailed trade-by-trade logs for each instrument and timeframe.
- `scanner.py`: The core institutional scanning logic.
- `backtest.py`: The simulation and results aggregation engine.
- `visualize.py`: Script for generating equity curves and performance charts.

---
**Generated on**: 2026-04-24
**System**: MMC Trading Backtest Engine v2.0

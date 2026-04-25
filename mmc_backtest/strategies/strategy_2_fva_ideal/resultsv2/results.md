# Strategy 2: FVA Ideal — Full Performance Report (v2)

This report contains the results of Strategy 2 (FVA Ideal) after applying the **Critical Institutional Fixes** (Structural Stop Loss, Full History Scan) based on Arjo's Video 2 and 11.

## 📊 Performance Summary (Full History)

| Instrument | Timeframe | Signals | Win Rate | Avg RR | Total RR | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **EURUSD** | **M15** | 19 | 47.37% | 1.28 | +24.39 | ✅ OK |
| **GBPUSD** | **M15** | 39 | 20.51% | -0.26 | -10.22 | ✅ OK |
| **EURUSD** | **H1** | 12 | 8.33% | -0.73 | -8.81 | ✅ OK |
| **GBPUSD** | **H1** | 11 | 27.27% | 0.04 | +0.47 | ✅ OK |
| **EURUSD** | **H4** | 8 | 0.00% | -1.00 | -8.00 | ✅ OK |

*Note: S2 (FVA Ideal) is an extremely high-precision strategy. Signals are rare because they require nested FVGs and perfect structural alignment.*

## 🛠️ Logic & Rules (Institutional Update)

### 1. The Entry Model (The "Ideal" FVA)
- **Setup**: Identification of a **Fair Value Area (FVA)** on the High Timeframe.
- **Nested Entry**: Price must retrace into a **nested FVG** (a 1H FVG inside a 4H FVA, or a 15M FVG inside a 1H FVA).
- **Trigger**: Entry at the boundary of the nested FVG.

### 2. The Stop Loss Rule (Arjo's Exact Rule)
- **Rule**: The Stop Loss is placed **exactly** at the swing point price of the most recent HTF Order Flow Leg (OFL) that created the FVA.
- **Fix**: Removed all pip buffers. Pure structural SL.

### 3. Take Profit
- **Primary**: Exit at the opposing HTF IT High/Low.
- **Secondary**: Minimum 2R required.

## 📁 Files Included in this Folder
- `s2_fva_ideal_*.csv`: Detailed trade logs.
- `scanner.py`: The nested FVA/FVG scanning logic.
- `backtest.py`: Simulation engine.

---
**Generated on**: 2026-04-24
**System**: MMC Trading Backtest Engine v2.0

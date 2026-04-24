# Strategy 3: Liquidity Sweep

## 1. Core Logic
Trade reversals triggered by a "Liquidity Sweep" (wicking through a previous IT High/Low or Session High/Low) followed by a structural break.

- **Objective**: Reversal / Liquidity Tap.
- **Timeframe**: ALL.
- **Entry Type**: Limit after the shift.

---

## 2. Institutional Rules (The Checklist)
- [x] **The Sweep**: Price must penetrate a previous swing level by at least 1-2 pips.
- [x] **REJECTION**: Candle must close back inside the range (forming a long wick).
- [x] **Shift**: A new FVG forming in the opposite direction of the sweep.

---

## 3. Configuration Parameters
Current active rules in `config.json`:
- `sweep_types_allowed`: ["SWEEP", "RUN"]
- `min_wick_ratio`: 0.3 (Wick must be 30% of candle size)
- `min_rr`: 2.0

---

## 4. Change Log & Evolution

### Phase 1: Institutional Strictness (2026-04-21)
- Only allowed strict "SWEEP" (immediate rejection).
- Result: 0 signals on many instruments.

### Phase 3: The Relaxation Sweep (2026-04-22)
- **Change**: Allowed "RUN" (price can run further before reversing).
- **Change**: Lowered wick requirement from 0.5 to 0.3.
- **Result**: Signals generated.

---

## 5. Performance Insights
Strategy 3 is essential for catching the "LOD" (Lowest of the Day) or "HOD" (Highest of the Day).

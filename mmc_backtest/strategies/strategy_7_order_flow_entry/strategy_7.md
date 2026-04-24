# Strategy 7: Order Flow Entry

## 1. Core Logic
The highest precision entry: Enter on a second or third sequential Order Flow Lag (OFL) within an active context area, using a full mechanical checklist audit.

- **Objective**: High-frequency, high-precision entry.
- **Timeframe**: Daily Context -> 15M Entry.

---

## 2. Institutional Rules (The Checklist)
- [x] **Full Audit**: Must pass 8+ out of 10 checklist items (Strict).
- [x] **Sequential Flow**: Multiple OFLs forming in the same direction.
- [x] **Liquidity Tap**: Moving towards a verified ERL.

---

## 3. Configuration Parameters
Current active rules in `config.json`:
- `min_checklist_pass`: 4 (Relaxed from 8)
- `fvg_types_allowed`: ["PFVG", "BFVG", "RFVG"]
- `min_rr`: 2.0

---

## 4. Change Log & Evolution

### Phase 1: Institutional Strictness (2026-04-21)
- Required 8/10 checklist pass.
- Result: Extremely high bar, very few signals.

### Phase 2: The Relaxation Sweep (2026-04-22)
- **Change**: Lowered bar to 4/10.
- **Change**: Allowed all FVG types.
- **Result**: Intensive scanning process to generate data.

---

## 5. Performance Insights
The "Gold Standard" of entries. Use this data particularly for training the "Filter" AI model.

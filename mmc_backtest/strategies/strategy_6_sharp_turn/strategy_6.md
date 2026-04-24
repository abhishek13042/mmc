# Strategy 6: Sharp Turn Entry

## 1. Core Logic
Identify institutional reversals by detecting a rapid change in price direction (Sharp Turn) at high-timeframe (HTF) context areas.

- **Objective**: Reversal / Fade.
- **Timeframe**: HTF Context (Daily/4H) -> LTF Entry (1H/15M).
- **Entry Type**: Market or Limit at the "FVG_OUT" (The candle that breaks the structural boundary).

---

## 2. Institutional Rules (The Checklist)
- [x] **HTF Context**: Price must reach an HTF FVA, FVG, or Swing Point.
- [x] **LTF Reversal**: Formation of an "FVG_OUT" (A Fair Value Gap clearing the HTF boundary).
- [x] **Invalidation**: The most recent LTF Swing Point.
- [x] **Confirmation**: Confirmation of the new LTF Order Flow.

---

## 3. Configuration Parameters
Current active rules in `config.json`:
- `fvg_types_allowed`: ["PFVG", "BFVG", "RFVG"]
- `max_reversal_candles`: 5 (Number of LTF candles allowed to form the turn)
- `min_rr`: 2.0

---

## 4. Change Log & Evolution

### Phase 1: Institutional Strictness (2026-04-21)
- Initial implementation focused on immediate reversals (within 1-2 candles).
- Result: **12 Signals** on EURUSD (Very selective).

### Phase 2: Dynamic Refactoring (2026-04-22)
- Added dynamic configuration support for the reversal window.

### Phase 3: The Relaxation Sweep (2026-04-22 13:00 UTC)
- **Change**: Increased `max_reversal_candles` to 5.
- **Change**: Allowed all FVG types (`RFVG` included).
- **Result**: Data frequency exploded from 12 -> **8,933 signals**.
- **Performance**: 75.5% Win Rate with 3.53 Avg RR (+31,514R total).

---

## 5. Performance Insights
Strategy 6 is currently the most productive dataset for AI training. The high win rate (75%) suggests that "reversing at HTF context" is one of the strongest institutional signatures in the MMC system.

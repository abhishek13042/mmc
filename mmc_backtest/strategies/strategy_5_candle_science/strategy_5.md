# Strategy 5: Candle Science

## 1. Core Logic
Use HTF candle "Confidence" (Video 5) to establish bias, then enter on LTF Order Flow alignment.

- **Objective**: Bias-driven continuation.
- **Timeframe**: Daily Candle Bias -> 1H Entry.

---

## 2. Institutional Rules (The Checklist)
- [x] **Candle Metrics**: Calculate body-to-wick ratio and range.
- [x] **Bias Classification**: BULLISH_CONFIDENT, BEARISH_HESITANT, etc.
- [x] **LTF Confirmation**: Must have a matching LTF OFL.

---

## 3. Configuration Parameters
Current active rules in `config.json`:
- `min_confidence_score`: 40
- `fvg_types_allowed`: ["PFVG", "BFVG"]

---

## 4. Change Log & Evolution

### Phase 1: Institutional Strictness (2026-04-21)
- Required 60+ confidence score.
- Result: 0 signals.

### Phase 3: The Relaxation Sweep (2026-04-22)
- **Change**: Lowered confidence bar to 40.
- **Change**: Allowed all PFVG/BFVG types.
- **Result**: Data frequency increased.

---

## 5. Performance Insights
Good for understanding the "Tone" of the market before looking for a setup.

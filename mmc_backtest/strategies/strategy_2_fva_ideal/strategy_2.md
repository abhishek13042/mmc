# Strategy 2: FVA Ideal Setup

## 1. Core Logic
Trade from "Ideal" Fair Value Areas (FVA) formed by specific market structure alignments (IT points + FVG overlap).

- **Objective**: Structural Context Trading.
- **Timeframe**: Daily/4H focus.
- **Entry Type**: Limit entry at FVA high/low.

---

## 2. Institutional Rules (The Checklist)
- [x] **Intermediate Term Points**: Must have an IT High/Low.
- [x] **FVA Building**: Defined by the space between two IT points or an IT point and an FVG.
- [x] **IDEAL Classification**: FVA must overlap with a PFVG and have a nested structure.
- [ ] **OFL Confluence (RELAXED)**: Direction should align with most recent OFL for high prob.

---

## 3. Configuration Parameters
Current active rules in `config.json`:
- `fva_types_allowed`: ["IDEAL", "GOOD"]
- `check_ofl_confluence`: False (Relaxed)
- `min_rr`: 2.0

---

## 4. Change Log & Evolution

### Phase 1: Institutional Strictness (2026-04-21)
- Focused only on "IDEAL" FVAs.
- Result: Very low signal count due to strict structural requirements.

### Phase 2: Dynamic Refactoring (2026-04-22)
- Implemented `FVA_TYPE_SCORES` and `FVA_IS_FLOD` probabilities.

### Phase 3: The Relaxation Sweep (2026-04-22 13:00 UTC)
- **Change**: Allowed "GOOD" FVAs (non-nested but overlapping).
- **Change**: Disabled strict OFL confluence check.
- **Result**: Data frequency increased.

---

## 5. Performance Insights
Strategy 2 is the most "Structural" strategy. It ensures you are trading from Fair Value rather than chasing price.

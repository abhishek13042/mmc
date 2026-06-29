# MMC Library — Architecture & Contract

This document is the **contract** for everyone (including subagents) building on
the MMC library. The goal: convert the 12 `transcripts/` videos into a coherent
Python library, **library first, then a backtester on top**.

## Stack & conventions

- **Python ≥ 3.10**, `pandas`, `numpy`. Tests with `pytest`.
- All code lives under the `mmc/` package. Tests under `tests/`.
- **Dataclasses + enums**, type hints everywhere, module + function docstrings.
- Every concept references its transcript, e.g. `# transcript 06 — Fair Value Gaps`.
- **Bars are addressed by integer position** (the `df.iloc` position), stored as
  `index` on detected objects. OHLC DataFrames have a sorted `DatetimeIndex` and
  float columns `open, high, low, close, volume`.
- **Do not re-define core types.** Import them from `mmc.core`. If you need a new
  shared field on a core type, add it there — don't fork.
- Detectors are **pure functions** over a DataFrame (and/or lists of core
  objects); no global state, no I/O except via `mmc.data`.
- Keep it **simple** (transcript 11/12: simplifying = turning 10 rules into 1).
  Only implement concepts from the MMC transcripts — no outside indicators.

## The OHLC DataFrame

```python
from mmc.data import load, load_all_timeframes, available_symbols
from mmc.core.types import Timeframe
df = load("EURUSD", Timeframe.H1)        # DatetimeIndex + open/high/low/close/volume
data = load_all_timeframes("XAUUSD")     # {Timeframe: DataFrame}
```

Raw CSVs are tab-separated, no header, at `mmc_backtest/data/raw/`. Symbols:
EURUSD, GBPUSD, XAUUSD. Timeframes: M5, M15, H1, H4, D1.

## Core API (the foundation — transcripts 01–03) — already built

Types (`mmc.core.types`):
`Direction` (BULLISH/BEARISH, `.opposite`, `.sign`), `Timeframe`,
`SwingType` (HIGH/LOW), `Zone` (`top, bottom, index, direction`,
`.is_premium/.is_discount/.midpoint/.contains`), `FairValueGap` (a `Zone` with
`c1/c2/c3_index`, `mitigated`, `mitigation_index`, `quality`), `SwingPoint`
(`index, price, kind`, `swept`), `StructurePoint` (`swing, kind, fvg`),
`StructurePointType` (ITH/ITL/STH/STL), `FairValueArea` (a `Zone` with
`start, end, overlapping_fvg, nested, quality`), `OrderFlowLag`
(`direction, swing, fvg, fva, flod, odd, lod`).

Detectors:
```python
from mmc.core import (
    find_swings, swing_highs, swing_lows,
    find_fvgs, mark_mitigation, unmitigated,
    intermediate_term_points, short_term_points,
    fair_value_areas, find_order_flow_lags, analyze,
)
```
`analyze(df)` returns `{swings, fvgs, intermediate, short_term, fvas, order_flow_lags}`.

**Polarity rule (uniform across the library):** bullish array = **discount**
(buy/continue up from it); bearish array = **premium** (sell/continue down).
A swing high is a premium array; a swing low is a discount array.
**No FVG → no order flow lag → no fair value area** (FVGs are superior).

## Layered build plan & module ownership

Each layer is its own subpackage. **Stay inside your module** + your test file;
do not edit `mmc/core` or another layer's files.

| Layer | Module | Transcripts | Depends on |
|------|--------|-------------|-----------|
| Foundation ✅ | `mmc/core`, `mmc/data` | 01–03 | — |
| Narrative | `mmc/narrative/` | 04, 06, 07 | core |
| Sweeps | `mmc/sweeps/` | 08 | core |
| Candle science | `mmc/candle_science/` | 05 | core |
| Timing | `mmc/timing/` | 09 | core |
| Context | `mmc/context/` | 10 | core, narrative, sweeps |
| Entry | `mmc/entry/` | 11 | core, context, timing |
| Top-down | `mmc/topdown/` | 12 | all above |
| Backtest | `mmc/backtest/` | — | entry |

## Definition of done (per layer)

1. Code under your `mmc/<layer>/` package with an `__init__.py` exporting a clean
   public API, docstrings, and transcript references.
2. Reuse core types/detectors — never reinvent FVG/swing/etc.
3. A `tests/test_<layer>.py` with focused unit tests on small synthetic
   DataFrames (use the `make_ohlc` fixture in `tests/conftest.py`).
4. `python -m pytest tests/test_<layer>.py -q` passes.
5. Do not break the existing suite (don't touch core/other layers).

Run the full suite with `python -m pytest -q` from the project root.

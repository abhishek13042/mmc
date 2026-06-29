# MMC — Money Making Concepts, as code

A Python library that converts the 12-video **Money Making Concepts (MMC)** series
by Arjo Janssens (full transcripts in [`transcripts/`](transcripts/)) into a
coherent, tested trading framework — **library first, then a backtester on top**.

Every concept maps to code, and every layer is built on the one below it. See
[`ARCHITECTURE.md`](ARCHITECTURE.md) for the full contract.

## Layers (dependency order)

| Layer | Package | Transcripts | What it does |
|-------|---------|-------------|--------------|
| Data | `mmc.data` | — | Load the raw OHLC CSVs into pandas |
| Core | `mmc.core` | 01–03 | Swings, Fair Value Gaps, market structure (ITH/ITL, STH/STL), Fair Value Areas, **order flow lags** |
| Narrative | `mmc.narrative` | 04, 06, 07 | FLOD / ODD / LOD, FVG quality (rejection/perfect/breakaway), FVA quality |
| Sweeps | `mmc.sweeps` | 08 | Liquidity sweep vs run, order-flow & candle-science sweeps, PCH/PCL |
| Candle science | `mmc.candle_science` | 05 | Respect / disrespect candles (order flow on a single candle) |
| Timing | `mmc.timing` | 09 | Time = volatility: sessions / kill zones, news / the big three |
| Context | `mmc.context` | 10 | Usual / unusual context areas (boundary → first opposing PD array) |
| Entry | `mmc.entry` | 11 | Sharp turns, order-flow entries, market-maker model, TF alignment, trade management |
| Top-down | `mmc.topdown` | 12 | Bias/arguments engine, filtering-process vs flow-trader styles, multi-pair ranking |
| Backtest | `mmc.backtest` | — | Event-driven trade simulation over `Entry` signals → stats + equity curve |

**Recurring core idea:** the market is always either *offering fair value* or
*seeking liquidity*, and **fair value gaps are superior** — no FVG → no order
flow lag → no fair value area.

## Install

Requires Python ≥ 3.10. From the project root:

```bash
pip install -e .          # installs mmc + pandas/numpy
pip install -e ".[dev]"   # also installs pytest
```

The raw market data (EURUSD / GBPUSD / XAUUSD at M5/M15/H1/H4/D1) lives under
`mmc_backtest/data/raw/` (tab-separated, no header).

## Quick start

```python
from mmc.core.types import Timeframe
from mmc.data import load
from mmc.core import analyze

# Load OHLC and run the foundation pass
df = load("EURUSD", Timeframe.H1)
structures = analyze(df)          # swings, fvgs, intermediate, short_term, fvas, order_flow_lags
```

Top-down bias + best pair (transcript 12):

```python
from mmc.topdown import top_down, best_pair, TraderStyle

result = top_down("XAUUSD", style=TraderStyle.FILTERING_PROCESS, bars=500)
print(result.narrative)           # direction → narrative → context

pick = best_pair(["EURUSD", "GBPUSD", "XAUUSD"], bars=500)
print(pick.symbol, pick.result.bias.summary)
```

Backtest a symbol end-to-end (transcript 11 trade rules — 1:2 RR, SL on the lag):

```python
from mmc.core.types import Timeframe
from mmc.backtest import backtest_symbol

res = backtest_symbol("EURUSD", Timeframe.H1, limit=2000)
print(res.summary())
```

A runnable version of the last example is in [`examples/run_backtest.py`](examples/run_backtest.py).

## Tests

```bash
python -m pytest -q
```

119 unit tests cover every layer (synthetic, deterministic fixtures plus
real-data loader checks).

## Notes

- Bars are addressed by **integer position** (`df.iloc` position); detected
  objects store that as `index`.
- Polarity is uniform everywhere: **bullish = discount** (buy/continue up),
  **bearish = premium** (sell/continue down). A swing high is a premium array.
- The detectors are reference implementations (clarity over micro-optimisation);
  some are O(n²), so cap bar counts (`limit=`) on large multi-thousand-bar runs.

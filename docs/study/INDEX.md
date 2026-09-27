# MMC — Study Set

A study companion to **MMC** ("Money Making Concepts" — the name of the price-action
methodology it codifies, taught across 12 transcripts by Arjo Janssens), a pip-installable
Python library that turns a discretionary price-action/ICT-style trading methodology into a
layered, dependency-ordered package: core primitives → narrative decomposition → liquidity
sweeps → candle science → timing → context → entry → top-down bias → event-driven
backtester.

## Reading order

| # | Document | Covers | Time |
|---|---|---|---|
| 0 | [00-how-to-study-this.md](00-how-to-study-this.md) | Study method, reading order, MMC-specific traps, things to say cold | 10–15 min |
| 1 | [01-concepts-from-zero.md](01-concepts-from-zero.md) | Every assumed concept — price action, market structure, liquidity sweeps, order flow, FLOD/ODD/LOD, event-driven backtesting, layered package design, the neural-net subsystem (and its real status) | 1.5–2 hrs |
| 2 | [02-the-layers-explained-slowly.md](02-the-layers-explained-slowly.md) | One real backtest run traced end to end through the actual layers and files, with numbered design decisions | 1.5–2 hrs |
| 3 | [03-the-test-suite-explained-slowly.md](03-the-test-suite-explained-slowly.md) | How the 136 tests are organized (synthetic vs real-data fixtures), representative tests read in full, why domain logic is kept separate from the backtester | 1–1.25 hrs |
| 4 | [04-results-and-how-to-defend-them.md](04-results-and-how-to-defend-them.md) | The real, verified test count, a real backtest result, known limitations, and scripted answers to the hard interview questions | 45–60 min |

**Total: roughly 5–6 hours** for a thorough first pass.

## In one paragraph

MMC is a pip-installable Python package (`pyproject.toml`, `pip install -e .`) that
encodes a 12-transcript price-action methodology into nine dependency-ordered
subpackages: `mmc.data` (loads raw tab-separated OHLCV for EURUSD/GBPUSD/XAUUSD),
`mmc.core` (swings, fair value gaps, intermediate/short-term structure points, fair value
areas, order flow lags — the vocabulary everything else is built from), `mmc.narrative`
(decomposes an order flow lag into FLOD/ODD/LOD — which price-delivery array actually
defended the move), `mmc.sweeps` (three independent lenses on "did price sweep or run":
liquidity, order-flow, candle-science), `mmc.candle_science` (single-candle
respect/disrespect classification), `mmc.timing` (kill-zone session windows), `mmc.context`
(usual FLOD/ODD/LOD context areas plus the unusual FVA-seeking-liquidity case),
`mmc.entry` (turns a context area into a concrete limit order with stop and target), and
`mmc.topdown` (accumulates cross-timeframe bias arguments). `mmc.backtest` sits on top and
is deliberately the only layer that knows about P&L: it consumes `Entry` objects and
replays them bar-by-bar with a deterministic, conservative same-bar-ambiguity rule,
producing R-multiple trade logs. The test suite currently contains **136 passing tests**
(not the 119 the README states — the number grew as the suite matured; see document 3),
split between synthetic deterministic fixtures (`tests/conftest.py::make_ohlc`) and
real-data loader checks that are skipped when the raw CSV directory is absent. Beyond the
resume's specific "core, market structure, liquidity sweeps, order flow, timing,
backtesting" claim, the repository also contains three large, real, but separately-tested
extensions — `mmc.strategies` (seven concrete trading strategies, S1–S7, not covered by
pytest), `mmc.evaluation` (a statistical strategy-qualification pipeline with real MT5
out-of-sample export tooling, 17 tests), and `mmc.brain` (a real, trained PyTorch
decision-network subsystem, untested by pytest and not declared as a package dependency)
— which document 4 covers honestly as scope beyond the resume line, not as padding.

Start at [00-how-to-study-this.md](00-how-to-study-this.md).

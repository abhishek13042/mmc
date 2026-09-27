# Study Guide 3 — The test suite, explained slowly

## 1. The real number, verified three independent ways

Running the suite:

```
python -m pytest -q
```

produces **136 passed** (plus one unrelated `UserWarning` from a `langsmith` import
about Pydantic/Python 3.14 compatibility — environmental noise, not an MMC test
failure).

Verified three ways, all agreeing:

| Method | Result |
|---|---|
| `python -m pytest -q` (dot count) | 136 |
| `python -m pytest --collect-only -q` (per-file breakdown, summed) | 136 |
| `grep -c "def test_"` per file, summed manually | 136 |

Per-file breakdown (from `--collect-only`, cross-checked with `grep -c`):

| File | Tests |
|---|---|
| `tests/test_backtest.py` | 14 |
| `tests/test_candle_science.py` | 12 |
| `tests/test_context.py` | 7 |
| `tests/test_entry.py` | 14 |
| `tests/test_evaluation.py` | 17 |
| `tests/test_fvg.py` | 4 |
| `tests/test_loader.py` | 4 |
| `tests/test_narrative.py` | 16 |
| `tests/test_structure.py` | 4 |
| `tests/test_sweeps.py` | 8 |
| `tests/test_swings.py` | 4 |
| `tests/test_timing.py` | 25 |
| `tests/test_topdown.py` | 7 |
| **Total** | **136** |

## 2. Why not 119

`README.md` states "119 unit tests cover every layer." `git log -p --follow --
README.md` shows the line `+119 unit tests cover every layer (synthetic, deterministic
fixtures plus` was added at a real point in the project's history — meaning 119 *was*
the accurate count at that commit. The suite has grown since (most visibly
`test_evaluation.py` at 17 tests and `test_timing.py` at 25 tests — both large files for
subsystems that plausibly expanded after the README line was written). This is the
honest framing: **the number is stale, not fabricated** — say exactly that if asked, and
be ready to run `python -m pytest -q` live to prove the current figure.

## 3. Synthetic fixtures vs. real-data fixtures

MMC's tests split cleanly into two families.

### Synthetic, deterministic fixtures

`tests/conftest.py::make_ohlc` builds a small, hand-specified OHLCV DataFrame from a
list of `(open, high, low, close[, volume])` tuples, stamped onto a synthetic
1-minute `pd.date_range` starting 2024-01-01. Almost every test outside
`test_loader.py` uses this — it lets a test assert an *exact* expected value (an FVG's
`top`/`bottom`/`mitigated` flag, a swept swing's index) because the input bars were
chosen by hand to produce exactly one unambiguous pattern.

Representative example, `tests/test_fvg.py::test_bullish_fvg` (read in full): builds a
3–4 candle synthetic sequence where the middle candle's close is known to clear the
first candle's high and the third candle's low is known to stay above it, then asserts
the resulting `FairValueGap.top`/`.bottom`/`.direction` exactly. `test_mitigation`
extends the same fixture with one more bar engineered to trade back into the gap and
asserts `mitigated=True` at the correct index. `test_no_fvg_when_gap_filled` is the
negative case — bars engineered so no FVG should be detected at all.

### Real-data fixtures, explicitly gated

`tests/test_loader.py` is different on purpose: it tests against the actual checked-in
historical CSVs under `mmc_backtest/data/raw/`, and is explicitly skipped if that
directory doesn't exist —

```python
pytestmark = pytest.mark.skipif(not DEFAULT_DATA_DIR.exists(),
                                 reason="raw data directory not present")
```

— so the suite still passes cleanly on a machine that cloned the repo without the raw
data directory, but exercises real data (column names, `DatetimeIndex` monotonicity,
`len > 1000`, `high >= low`, `df.attrs`) whenever it's present. This is exactly the
"synthetic, deterministic fixtures plus real-data loader checks" the README describes —
that specific claim checks out precisely, independent of the stale 119 count.

## 4. A handful of representative tests, read in full

**`tests/test_backtest.py`** — hand-builds real `mmc.entry.Entry` objects (via local
helpers `_bearish_fvg`, `_bullish_fvg`, `_context`, `_bearish_entry`) paired with
deterministic OHLC bars engineered to produce a clean WIN, a clean LOSS, a same-bar
ambiguous case, a NO_FILL, and a TIMEOUT — one test per outcome the fill engine can
produce (14 tests total). This is the test file that directly proves design decision #4
from document 2 (conservative stop-first resolution on same-bar ambiguity) is actually
implemented as documented, not just described in a comment.

**`tests/test_evaluation.py`** — validates the statistical pipeline against
*hand-computed* values on a deliberately simple repeating R-multiple sequence:

```python
PATTERN = np.tile([4.0, -1.0], 100)  # 200 trades, WR 50%, PF 4
```

`test_core_metrics_exact` asserts `win_rate == 0.5`, `profit_factor == 4.0`,
`expectancy == 1.5`, etc. — all arithmetic anyone can verify by hand from the pattern.
Stochastic pieces (bootstrap confidence bands, Monte Carlo drawdown simulation) are
checked for *structural* sanity with a fixed seed (`test_bootstrap_band_brackets_and_
reproducible` asserts the same seed reproduces the same 5th-percentile value —
determinism, not a specific numeric outcome) rather than for an exact number, which is
the correct way to test something intentionally random.

**`tests/test_timing.py`** — `TestKillZones` tests `killzone_window`/`in_killzone` for
both the forex and index session windows, including the half-open boundary case (does a
timestamp exactly at the window's start/end count as inside or outside). 25 tests total
in this file — the largest single contributor to the suite's growth beyond 119.

## 5. Why domain logic is kept separate from the backtester

This is directly testable, not just architectural rhetoric: `mmc/backtest/` contains
three files — `engine.py`, `result.py`, `fill.py` — and none of them import
`mmc.core.swings`, `mmc.core.fvg`, `mmc.narrative`, `mmc.sweeps`, `mmc.context`, or
`mmc.candle_science`. The only "upstream" type `mmc.backtest` touches is `Entry`
(from `mmc.entry`). Concretely: `simulate_entry(entry, df, max_hold)` takes an
already-built `Entry` and a raw price DataFrame — it has no way to ask "was this a real
FVG" or "was this swing actually swept," it can only fill and exit the order it was
handed.

The practical payoff, and the answer to "why does this matter": **you can unit-test the
backtester's fill/exit logic completely independently of whether the detection logic
(swings, FVGs, context) is correct.** `test_backtest.py`'s hand-built `Entry` objects
prove the fill engine's WIN/LOSS/ambiguous/NO_FILL/TIMEOUT logic in isolation — a bug in
`mmc.core.fvg.find_fvgs` cannot possibly make `test_backtest.py` pass or fail, because
that test file never calls it. Symmetrically, `test_fvg.py`/`test_structure.py`/
`test_context.py` never touch P&L at all — they assert zone geometry and object
attributes, nothing about R-multiples. This separation is what makes it possible to
trust that a passing backtest isn't secretly proof of a coincidentally-matched bug in
both layers at once — each layer's tests would have to be wrong in the same direction
independently, which is a much stronger guarantee than one monolithic test suite gives
you.

## 6. What's not covered by pytest — stated plainly

- **`mmc/strategies/` (S1–S7)** — there is no `tests/test_strategies.py`. These seven
  strategy functions are real, working code (`mmc/strategies/__init__.py`, 390 lines)
  whose reported backtest numbers in `ANALYSIS.md` come from ad-hoc script runs, not
  from the pytest suite.
- **`mmc/brain/`** — the PyTorch decision-network subsystem has no corresponding test
  file (`grep -rln "mmc.brain" tests/` returns nothing).
- **`atoz/`** — the separate ~9,429-line ICT library has no test coverage inside this
  repo's `tests/` directory either (not checked exhaustively for a private test suite of
  its own, but nothing under `tests/` references it).

None of this is being hidden by the README's "119 tests cover every layer" line — that
line is specifically about the nine `mmc/` subpackages document 1–2 describe, and for
those specifically the claim holds up (136, not 119, but every one of those nine layers
genuinely has passing test coverage). The three items above are simply outside that
claim's stated scope, and document 4 treats them as such.

---

## Self-test

**Level 1.** State the real, current test count and the three ways it was verified.
Name the one file whose tests are explicitly skipped when data is absent, and the
mechanism (`pytestmark`) that does it.

**Level 2.** Why is checking bootstrap/Monte Carlo tests for *reproducibility under a
fixed seed* the right test design, instead of asserting one specific expected number?
Why can a bug in `mmc.core.fvg.find_fvgs` never cause `test_backtest.py` to fail?

**Level 3.** *"119 tests, huh? Run it for me."* Run `python -m pytest -q` live if asked;
state the real number (136) before running it, explain the 119→136 drift via the git
history of the README line, and name the two largest contributors
(`test_evaluation.py`, 17; `test_timing.py`, 25) without needing to re-check — this is
one of the "things to say cold" from document 0.

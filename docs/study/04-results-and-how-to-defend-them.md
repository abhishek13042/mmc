# Study Guide 4 — Results, and how to defend them

## 1. What's demonstrably working

**The test suite.** `python -m pytest -q` → **136 passed, 0 failed**, verified in this
session. Every one of the nine `mmc/` subpackages the resume describes (core through
backtest, plus narrative/context/entry/topdown which sit between them) has real,
passing, mostly-synthetic-plus-some-real-data test coverage. See document 3 for the full
breakdown.

**A real, reproducible backtest.** `python examples/run_backtest.py EURUSD H1 2000`,
captured live in this session:

```
signals processed : 898        trades (filled)   : 836      no-fills : 62
wins / losses      : 370 / 466  win rate          : 44.3%
expectancy (R)     : +0.328     total (R)         : +274.000
average RR         : 2.00       profit factor     : 1.59      max consec losses : 88
```

This is one run, one symbol, one timeframe, one 2000-bar window, at a fixed `rr=2.0` —
it is evidence the pipeline runs end to end and produces internally consistent numbers
(document 2 §8's arithmetic check), **not** a claim of a validated trading edge across
symbols, timeframes, or out-of-sample data. Treat it exactly that way if asked.

**A pip-installable package.** `pyproject.toml` genuinely declares `[project] name =
"mmc"`, `dependencies = ["pandas>=2.0", "numpy>=1.24"]`, and
`[tool.setuptools.packages.find] include = ["mmc*"]` — `pip install -e .` works as
documented, for the `pandas`/`numpy`-only core of the package.

## 2. Known limitations — declared, with reasons

| Limitation | What's actually known | Why it's stated this way |
|---|---|---|
| README's "119 unit tests" | Real count is 136, verified three ways | Stale, not fabricated — traced via `git log -p --follow -- README.md` to the commit where 119 was accurate |
| S4 (ODD strategy) historical "zero trades" bug | `ANALYSIS.md` documents the bug; current `mmc/context/usual.py` contains an explicit code comment referencing it and logic that does build FVAs and tag `defense="ODD"` | Not independently re-verified by re-running S4 to confirm a non-zero trade count in this session — say "the fix appears to be present in the code; I have not re-run S4 to confirm the count" if asked, not "it's fixed" |
| `mmc/strategies/` (S1–S7) | Real, working code; no `tests/test_strategies.py` | Backtest numbers in `ANALYSIS.md` come from ad-hoc script runs, not pytest |
| `mmc/brain/` (PyTorch decision network) | Real architectures, real trained `.pt` weights, real MT5 fleet logs; no pytest coverage; `torch` not declared in `pyproject.toml` | Functional but outside both the tested core and the declared install contract |
| Confidence numbers 65%/78%/88% (FLOD/ODD/Unusual) | Presented in `NEURAL_NETWORK_GUIDE.md`/`ANALYSIS.md` as the methodology's stated confidence hierarchy | Not independently reproduced from a live model run in this session — describe as documented, not measured-here |
| `atoz/` library (~9,429 LOC) | Present in the repo, wholly separate type system from `mmc.core`, not referenced by README/ARCHITECTURE/the resume bullet | Real code, but outside the scope of what the resume claims about MMC |
| Single-run backtest example | One symbol/timeframe/window at fixed RR | Not a multi-symbol, multi-timeframe, out-of-sample validated result on its own |

## 3. How to validate trading logic without live capital — the project's real answer

This is worth having fully prepared, because it's the question most likely to expose a
shallow answer. MMC's actual, built answer has three layers, in increasing rigor:

1. **Deterministic unit tests against hand-built fixtures** (document 3) — prove the
   *mechanics* (FVG detection, fill logic, metric arithmetic) are correct against known
   inputs, independent of whether the trading idea itself has edge.
2. **Historical backtesting** (`mmc.backtest`, document 2) — replay the exact same
   detection and entry logic against real historical OHLCV data
   (`mmc_backtest/data/raw/`), producing R-multiple statistics like the captured
   EURUSD H1 run above.
3. **`mmc.evaluation`** — a real, separate statistical qualification pipeline
   (`mmc/evaluation/README.md`) that goes beyond the four "vanity numbers" (win rate,
   profit factor, expectancy, total R) a console backtest prints. It applies
   *pre-committed* pass/fail gates — sample size N ≥ 100, bootstrap 5th-percentile
   profit factor > 1.2, recovery factor > 2.0, in-sample/out-of-sample profit-factor
   decay < 30% — and has a real out-of-sample path: `examples/mt5_oos_test.py` exports
   real trade logs from a live MT5 feed (with a fixed spread cost applied) without
   risking capital, specifically to compare in-sample training numbers
   (`mmc/brain/weights/RESULTS_TABLE.csv`) against forward/live-feed performance. This
   is genuinely more rigorous than "backtest and eyeball it" — 17 tests in
   `tests/test_evaluation.py` validate the metric math itself against hand-computed
   values (document 3 §4).

The honest caveat to pair with this: the MT5-live-feed OOS export requires an actual
MT5 terminal connection, which was not exercised in this session — the claim is "the
author built a real path to out-of-sample validation," not "I personally ran it and
confirmed a live result."

## 4. Why layer it this way instead of one monolithic module

Three concrete, code-grounded reasons, not abstractions:

1. **Independent testability.** Document 3 §5 shows this directly: `mmc.backtest`
   imports nothing from `mmc.core`/`narrative`/`sweeps`/`context` — only `Entry`. A bug
   in FVG detection literally cannot make a backtest-fill test pass or fail, because
   that test never calls the FVG detector. In one monolithic module, that isolation is
   impossible to guarantee by construction.
2. **Enforced dependency direction.** `ARCHITECTURE.md`'s rule ("stay inside your
   module... do not edit `mmc/core` or another layer's files") is not just a comment —
   it's true of the actual import graph (document 1 §16). This means a change to, say,
   `mmc.context` can never silently break `mmc.core`'s behavior, because nothing in
   `mmc.core` imports anything above it.
3. **Independent evolvability of the trading idea vs. the execution engine.** Seven
   different strategies (`mmc.strategies` S1–S7) reuse the *same* `mmc.backtest` engine
   with different context/entry combinations — the backtester's fill/exit logic was
   written and tested once and never needed to change as the trading ideas on top of it
   multiplied.

## 5. What would break if you added a new layer

Grounded directly in the dependency table (`ARCHITECTURE.md`, verified against real
imports in document 1 §16): a new layer must only import from layers *below* it in the
existing order (`data → core → {narrative, sweeps, candle_science, timing} → context →
entry → topdown → backtest`). Concretely:

- A new layer inserted **between `context` and `entry`** (say, a risk-sizing layer) would
  need `mmc.entry` to start importing it, and would itself be restricted to importing
  only `mmc.core`/`narrative`/`sweeps`/`context`/`timing` — it could not reach into
  `mmc.backtest` or `mmc.topdown` without inverting the dependency direction the whole
  package relies on.
- If a new layer instead tried to import `mmc.core` and get imported *by* `mmc.core` (a
  cycle), that would directly violate the rule that makes `mmc.core`'s own test suite
  (`test_fvg.py`, `test_swings.py`, `test_structure.py`) able to run in complete
  isolation from everything built on top of it — those tests currently import nothing
  above `mmc.core`.
- Concretely, nothing about existing tests would need to change for a genuinely
  lower-layer addition (e.g., a new data source under `mmc.data`) — but a layer inserted
  in the *middle* of the chain would require every test file for layers above the
  insertion point to be re-examined for whether they now need the new layer's output as
  an input, since (per document 3 §5) each layer's tests are built assuming a specific,
  fixed set of upstream inputs.

## 6. Hard questions, scripted answers

**Q: "The resume says 119 tests. I count 136. Which is right?"**
A: "136 is the current, accurate count — verified by running `python -m pytest -q`
myself, and cross-checked with `--collect-only` and a manual per-file `grep`. 119 was
accurate at an earlier commit; I can show you in `git log -p --follow -- README.md`
exactly where that line was added. The suite grew afterward, mostly in
`test_evaluation.py` (17 tests) and `test_timing.py` (25 tests) — the README line just
never got updated."

**Q: "Is the neural network actually used, or is that just documentation?"**
A: "It's real — `mmc/brain/` has real PyTorch `nn.Module` architectures and real trained
weight files on disk per symbol and timeframe, plus MT5 live-fleet logs showing it's
been run against live data. Two honest caveats: it has no pytest coverage, and `torch`
isn't declared in `pyproject.toml`'s dependencies, so it's functional but sits outside
both the tested core and the officially packaged install path. And the specific
confidence percentages quoted in the docs — I'm presenting those as the methodology's
documented figures, not numbers I personally reproduced from a live model run."

**Q: "What's the actual measured win rate / edge?"**
A: "One real, reproducible run — EURUSD H1, last 2000 bars — landed at 44.3% win rate,
+274R total, 1.59 profit factor, at a fixed 2:1 reward-to-risk. That clears the ~33%
break-even threshold a 2R target implies. That's one symbol, one timeframe, one window
though — it's evidence the pipeline works end to end and the numbers are internally
consistent, not a claim of validated edge across markets or out-of-sample time."

**Q: "How do you know the backtest isn't just detecting its own bugs and calling it a
strategy?"**
A: "Because the backtester and the detection logic are tested completely separately.
`mmc.backtest`'s own test file hand-builds `Entry` objects directly — it never calls
`mmc.core.fvg.find_fvgs` at all — so a bug in FVG detection can't make the fill-engine
tests pass or fail, and vice versa: the FVG/structure tests never touch P&L. Two
independently-passing test suites agreeing is a much stronger signal than one suite that
could be silently compensating for itself."

**Q: "What's broken or incomplete right now?"**
A: "The ODD strategy had a documented zero-trades detection bug — the current context
code has logic and a comment addressing it, but I haven't re-run that specific strategy
to confirm it now produces trades, so I'd call that 'apparently addressed, not
independently re-verified.' Separately, `mmc.strategies` — the seven concrete trading
strategies — have no pytest coverage; their reported numbers come from ad-hoc script
runs, not the test suite."

**Q: "Why should I trust a price-action methodology turned into code — isn't this
subjective by nature?"**
A: "That's exactly the design goal — turning something normally taught by eye
(watch the chart, feel the reaction) into deterministic, hand-testable rules: a Fair
Value Gap is a precise 3-candle inequality, a swing point is a precise fractal
comparison, mitigation is the first bar whose range trades into a zone. Every one of
those has a hand-built synthetic test with an exact expected output. It doesn't
guarantee the underlying trading idea has edge — that's what the backtest and the
`mmc.evaluation` gates are for — but it does mean the *rules themselves* aren't fuzzy or
inconsistently applied."

**Q: "What would you build next?"**
A: "Test coverage for `mmc.strategies` — it's the layer that actually produced the
`ANALYSIS.md` numbers and currently has zero pytest coverage, which is the biggest gap
relative to how central it is. Second, declaring `torch` as an optional dependency
(`[project.optional-dependencies]`) so `mmc.brain` is installable through the normal
package contract instead of requiring a manual `pip install torch`."

## 7. Approaches noted as limitations, not hidden

- The 65/78/88% brain confidence figures — documented, not re-measured here (§2, §6).
- The S4 ODD bug — apparently addressed in code, not re-confirmed by re-running the
  strategy (§2, §6).
- `atoz/` — a real, separate ~9,429-line ICT library in the repo, unconnected to
  `mmc.core`'s type system and outside the resume's specific claim about MMC (§2).

## 8. Five-minute pitch

> "MMC takes a discretionary price-action trading methodology — taught across twelve
> video transcripts — and turns it into a pip-installable Python package with nine
> dependency-ordered layers: core primitives like swing points and Fair Value Gaps,
> narrative decomposition into first/overlapping/last lines of defense, three
> independent sweep classifications, candle-level and session-level timing filters,
> context-area construction, concrete entry signals, cross-timeframe bias, and finally a
> deterministic event-driven backtester that only ever consumes already-built entry
> signals — it never re-derives trading logic itself, which is what lets its fill
> engine be unit-tested completely independently of whether the detection logic is
> correct. 136 tests currently pass — I verified that myself rather than trusting the
> README's stale 119 figure — split between hand-built deterministic fixtures and real
> historical-data checks. A real captured backtest run on EURUSD H1 landed at 44.3% win
> rate and +274R at a fixed 2:1 reward-to-risk, comfortably above the ~33% break-even
> line that ratio implies. Beyond the core package, the repo also includes a real,
> separately-tested statistical strategy-qualification pipeline with a live MT5
> out-of-sample export path, and a real, trained PyTorch decision-network subsystem —
> both genuine, both outside the pytest-covered core, and I can tell you exactly where
> each one's coverage ends."

---

## Self-test

**Level 1.** State the real test count and the real captured backtest numbers from
memory, without notes.

**Level 2.** Explain *why* layering enables independent testability, using the specific
fact that `mmc.backtest` never imports `mmc.core`.

**Level 3.** Deliver the five-minute pitch above out loud, unscripted, then answer a
follow-up you pick at random from §6 without looking at the written answer first.

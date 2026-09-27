# Study Guide 0 — How to study this project

MMC is a **domain-specific library replication**: it takes a discretionary,
video-taught trading methodology and turns it into deterministic, testable Python code.
Read this document first — fifteen minutes — before any source file.

---

## 1. The standard

**You have understood something when you can explain it, from memory, to someone who does
not trade, and survive their follow-up question.**

That includes explaining a Fair Value Gap without hand-waving, tracing exactly which
function call produces a specific number in a backtest summary, and being honest about
what the 136 passing tests actually prove versus what they don't.

## 2. The method

1. Read one section.
2. Close it and explain it **out loud**, from memory.
3. Notice exactly where you go vague — that vagueness is the gap, not a style problem.
4. Go back to that specific gap, not the whole section.

## 3. The documents, in order

| Read | Document | Why here |
|---|---|---|
| 1st | `01-concepts-from-zero.md` | Every term the codebase assumes — price-action vocabulary (swings, FVGs, structure points), the FLOD/ODD/LOD narrative, sweep classification, event-driven backtesting, and layered package design, in dependency order |
| 2nd | `02-the-layers-explained-slowly.md` | One real backtest run (EURUSD H1, 2000 bars) traced end to end through the actual nine layers, file by file, function by function |
| 3rd | `03-the-test-suite-explained-slowly.md` | How the 136-test suite is organized, several representative tests read in full, and why the backtester never re-derives trading logic |
| 4th | `04-results-and-how-to-defend-them.md` | The real, verified test count and backtest numbers, known limitations, and scripted answers to the questions an interviewer will actually ask |

**Total: roughly 5–6 hours** for a thorough first pass.

## 4. The one thing that makes this project different from a typical trading-bot repo

Most hobby trading-bot repos are one big script: indicators, entry logic, and
backtesting P&L all tangled in the same function. **MMC inverts that on purpose.**
`ARCHITECTURE.md` states a hard rule — *"Stay inside your module. Do not edit `mmc/core`
or another layer's files."* — and every subpackage under `mmc/` only imports from layers
strictly below it (verified against real imports, not just the docs: `mmc.context`
imports `mmc.core`, `mmc.narrative`, `mmc.sweeps`; `mmc.entry` additionally imports
`mmc.timing`; `mmc.backtest` imports only `mmc.entry`'s public `Entry` type and never
touches detection logic). The payoff: `mmc.backtest` cannot "cheat" — it has no way to
peek at a swing or a Fair Value Gap directly, it can only fill the `Entry` objects the
layers above it produced. That separation is the real answer to "how do you know your
backtest isn't just curve-fit to itself" — see document 3 §4 and document 4.

## 5. Traps

**Trap 1 — treating "market structure" as one flat concept.** MMC distinguishes swing
points (the raw fractal highs/lows) from *structure points* (`ITH`/`ITL`/`STH`/`STL` —
swings that qualify under stricter rules) from *Fair Value Areas* (the zone between two
opposing structure points). Conflating these three in an answer is the single most common
way this topic falls apart under questioning. Document 1 builds them in that order for a
reason — do not skip ahead.

**Trap 2 — trusting the README's "119 unit tests" line.** It was accurate at an earlier
commit (verifiable in `git log -p --follow -- README.md`) but the suite has since grown.
Running `python -m pytest -q` today collects **136 tests, all passing**. Document 3 covers
the real per-file breakdown and why the number grew — do not repeat "119" from memory
without checking; the real, current number is what an interviewer's own clone of the repo
would show.

**Trap 3 — assuming everything in the repository belongs to the resume's claim.** The
resume bullet describes six layers: core, market structure, liquidity sweeps, order flow,
timing, backtesting. The real `mmc/` package has nine subpackages (it also has
`narrative`, `context`, `entry`, `topdown` sitting between "order flow" and
"backtesting"), and the wider repository additionally contains `mmc/strategies`
(untested by pytest), `mmc/evaluation` (tested, 17 tests, a real statistical
qualification pipeline), `mmc/brain` (a real, trained PyTorch subsystem, untested by
pytest and not a declared package dependency), and a wholly separate `atoz/` library
unconnected to `mmc`'s type system. None of this is fabricated — all of it is real code
that runs — but conflating "what's in the repo" with "what the resume claims" is a trap.
Document 4 draws that line explicitly.

**Trap 4 — assuming the neural-network guide describes a trained, validated model whose
output numbers you can quote as measured results.** `mmc/brain/` is real (real
`torch.nn` architectures, real trained `.pt` weight files per symbol/timeframe/variant).
But the specific confidence percentages quoted in `NEURAL_NETWORK_GUIDE.md` and
`ANALYSIS.md` (FLOD 65% / ODD 78% / Unusual 88%) describe the *methodology's* stated
confidence hierarchy from the source material, not a number this session re-derived from
a model's live output — treat them as documented, not independently re-verified, and say
so if asked. See document 1 §9 and document 4.

## 6. Answering a question you cannot answer

1. Say the boundary: "I don't know that one exactly."
2. Say what's adjacent: "I know `mmc.timing.sessions` handles kill-zone windows for
   forex and index; I haven't traced the news/volatility-event scoring in
   `mmc.timing.news` line by line."
3. Say where to look: "`mmc/timing/news.py` — thirty seconds to check."

## 7. Six things to say cold

1. **What it is.** "A pip-installable Python library that codifies a price-action
   trading methodology — swing points, Fair Value Gaps, liquidity sweeps, order flow —
   into a layered package, plus a deterministic event-driven backtester on top."
2. **The layer rule.** "Each subpackage only imports from layers below it — `mmc.core`
   never imports from `mmc.context`, and the backtester only ever consumes `Entry`
   objects, it never re-derives trading logic itself."
3. **The central object.** "An `OrderFlowLag` — a swing paired with the Fair Value Gap
   that confirms it — is the one object almost everything downstream is built from:
   narrative decomposition, context areas, and entries all consume it."
4. **The ambiguous-bar rule.** "When a single bar's range would hit both the stop and
   the target, the backtester conservatively assumes the stop was hit first and flags the
   trade `ambiguous=True` — it never silently assumes the better outcome."
5. **The test count, precisely.** "136 tests, all passing, verified by running
   `python -m pytest -q` — not the 119 the README states; that number is stale, not
   fabricated, and I can show the git history that proves it."
6. **The real example.** "A 2000-bar EURUSD H1 backtest through `examples/run_backtest.py`
   produced 836 filled trades, a 44.3% win rate, and +274R total at a fixed 2R target —
   numbers I generated myself, not copied from a report."

## 8. The whole project in one breath

> Twelve transcripts of a discretionary price-action methodology get turned into
> deterministic code: swing points and Fair Value Gaps (`mmc.core`) combine into
> order flow lags, which `mmc.narrative` decomposes into FLOD/ODD/LOD defense zones,
> while `mmc.sweeps` independently classifies whether a broken level was swept or run
> and `mmc.candle_science` classifies single-candle respect/disrespect — all of that
> feeds `mmc.context`, which builds tradeable usual and unusual context areas, `mmc.entry`
> turns a context area into a concrete limit order with a stop and an RR-based target,
> and `mmc.topdown` layers cross-timeframe bias on top — then `mmc.backtest`, which knows
> nothing about any of that detection logic, replays the resulting `Entry` objects
> bar-by-bar with a deterministic, conservative fill-and-exit simulation to produce
> R-multiple results. 136 tests currently pass, split between synthetic deterministic
> fixtures and real historical-data checks, and a real captured run
> (EURUSD H1, 2000 bars) landed at +274R with a 44.3% win rate at 2R target — on top of
> that core, three further real subsystems (`mmc.strategies`, `mmc.evaluation`,
> `mmc.brain`) extend the project well beyond what the resume line describes, with
> differing levels of test coverage that document 4 states plainly.

---

## Self-test

**Level 1.** State the four-step study method. Name the layer that is only ever allowed
to consume `Entry` objects, never detection logic directly.

**Level 2.** Why does §4 say MMC "inverts" the typical trading-bot repo's structure?
Concretely, which two files enforce that rule, and what would break if `mmc.backtest`
imported `mmc.core` directly to re-derive a swing itself?

**Level 3.** *"Your README says 119 unit tests, but I count something else when I clone
this — which is it?"* Answer using §5 Trap 2 and document 3 directly: 136, verified by
running `python -m pytest -q` and cross-checked with `--collect-only` and a manual
`grep -c "def test_"` per file; the 119 figure was accurate at an earlier commit
(traceable in `git log -p --follow -- README.md`) and simply went stale as the evaluation
layer and the timing tests grew — not a fabricated number.

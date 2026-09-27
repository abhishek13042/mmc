# Study Guide 1 — Concepts, from zero

Every concept MMC's code assumes, built up in the order the codebase itself depends on
them. Nothing here is used before it's defined. Where a term maps directly to a class,
function, or file, that mapping is given immediately — go look at the file once, then come
back.

---

## 1. Price-action trading, in one paragraph

Price-action trading makes decisions from the shape of raw price bars (candles) —
where highs and lows sit relative to each other, where gaps form, which levels get
revisited — rather than from lagging indicators (moving averages, RSI, etc.). MMC
implements one specific, video-taught flavor of this (ICT/"smart money"-adjacent,
credited in the repo to a 12-part transcript series by Arjo Janssens — see
`transcripts/01_pd_arrays.md` through `transcripts/12_top_down_analysis.md`). The
methodology's central claim is that price is delivered through recognizable "PD arrays"
(premium/discount arrays — zones where price is statistically likely to react), and that
you can build a mechanical, backtestable process for spotting when one of those arrays is
about to be defended or broken.

## 2. OHLC bars and the DataFrame contract

Every function in MMC operates on a pandas DataFrame with columns `open, high, low,
close` (optionally `volume`), a `DatetimeIndex`, and **integer positional indexing**
everywhere internally — a "swing at index 42" means `df.iloc[42]`, not a timestamp. This
is stated as a hard contract in `ARCHITECTURE.md` and is why almost every function
signature in the codebase takes a plain `df: pd.DataFrame` and returns objects carrying
an `index: int` field rather than a timestamp.

`mmc/data/loader.py::load(symbol, timeframe)` is where real data enters this contract: it
reads a tab-separated, headerless CSV from `mmc_backtest/data/raw/`, builds a sorted
`DatetimeIndex`, coerces OHLC columns to `float`, and stamps `df.attrs["symbol"]` /
`df.attrs["timeframe"]`. `available_symbols()` discovers symbols by regex over the raw
filenames. Real CSVs exist on disk for EURUSD, GBPUSD, and XAUUSD at M5/M15/H1/H4/D1 —
this is not a synthetic-only project; there is real historical price data checked into
the repo.

## 3. Swing points — the raw fractal

A **swing point** (`mmc.core.swings.find_swings`) is the most primitive structure MMC
detects: a 3-bar (by default `left=1, right=1`) fractal — a bar whose high is greater
than both neighbors' highs (a *swing high*) or whose low is less than both neighbors'
lows (a *swing low*). This is a single O(n) pass over the DataFrame. Every swing high
carries `SwingType.HIGH`; every swing low, `SwingType.LOW`.

**Polarity convention** (this trips people up — memorize it): a swing **high** sits in
*premium* (the array a seller would defend, i.e. a **bearish** array); a swing **low**
sits in *discount* (a **bullish** array). `SwingPoint.direction` returns `BEARISH` for a
high and `BULLISH` for a low. This convention is consistent everywhere downstream —
`Zone.is_premium` / `Zone.is_discount` follow the same rule.

## 4. Fair Value Gaps (FVGs) — the imbalance

A **Fair Value Gap** (`mmc.core.fvg.find_fvgs`) is a 3-candle pattern where the middle
candle creates a gap the outer two candles don't overlap — a *bullish* FVG is
`close[c2] > high[c1] and low[c3] > high[c1]` (price left a hole below it going up); a
bearish FVG is the mirror. An FVG is a `Zone` subclass (`top`, `bottom`, `direction`,
plus `c1_index/c2_index/c3_index`), and it can later be **mitigated**
(`mark_mitigation`, O(n²) worst case) — the first later bar whose range trades back into
the gap. An `unmitigated` FVG is one price hasn't revisited yet.

FVGs are the single object that everything else in MMC hinges on. The methodology's
implicit rule, stated directly in a code comment in `mmc/context/usual.py`, is **"no
FVG → no order flow lag"** — a bare swing point by itself proves nothing; it only becomes
tradeable once an FVG confirms it.

## 5. Structure points — ITH/ITL and STH/STL

Not every swing matters equally. `mmc.core.structure.py` promotes qualifying swings into
two stricter categories:

- **Intermediate-Term High/Low (ITH/ITL)** — a swing high that is itself *lower* than
  the nearest swing highs on both sides of it (ITL is the mirror: a swing low higher than
  its neighbors). This is a pure geometry rule over the swing sequence; no FVGs involved.
- **Short-Term High/Low (STH/STL)** — a swing point followed by an *opposing* FVG within
  a small lookahead window (default `window=3` bars). Read literally from
  `mmc/core/structure.py`: an STH is a swing **high** confirmed by a **bearish** FVG
  forming shortly after it (the code's own comment: `wanted = Direction.BEARISH if
  s.kind is SwingType.HIGH else BULLISH`). This is the first place an FVG is required to
  promote a bare swing into something meaningful.

Both live in the `StructurePoint` dataclass (`swing`, `kind: StructurePointType`,
optional `fvg`).

## 6. Fair Value Areas (FVAs) — the zone between two arrays

`mmc.core.structure.fair_value_areas(points)` pairs consecutive *opposing* structure
points (an ITH followed by an ITL, or vice versa) into a `FairValueArea` — a `Zone`
representing the whole price range between two structure levels, not just one FVG. This
is the "bigger picture" zone the narrative layer (§8 below) checks price against.

## 7. Order Flow Lags — the central object

`mmc.core.structure.find_order_flow_lags(swings, fvgs, window=3)` pairs each FVG with the
**nearest preceding same-polarity swing** within a small window — a bearish FVG pairs
with a swing high, a bullish FVG with a swing low — into an `OrderFlowLag` (`direction`,
`swing`, `fvg`, plus later-filled `fva`, `flod`, `odd`, `lod`). This is the single object
nearly every downstream layer consumes: narrative decomposition, context-area
construction, and entries are all built from `OrderFlowLag` instances. If you understand
one class in this codebase, understand this one.

`mmc.core.structure.analyze(df, window=3)` is the one-call convenience function that runs
the whole `mmc.core` pipeline (swings → fvgs → ITH/ITL → STH/STL → fvas →
order_flow_lags) and returns all of it as a dict — this is the function document 2 traces
line by line.

## 8. FLOD / ODD / LOD — the narrative decomposition

`mmc.narrative.lag.decompose_lag(lag, df, fvas)` answers "which array actually defended
this move, and in what order?" It always sets `lag.lod = lag.swing` (the swing itself is
always the **Last Line Of Defense**). Then, if the lag has an overlapping `FairValueArea`
attached, it looks at which boundary — the FVG or the FVA — price would retrace into
*first*; whichever is hit first becomes the **First Line Of Defense (FLOD)**, the other
becomes the **Overlapping Defense (ODD)**. If there's no FVA at all, the FVG is *both*
FLOD and ODD (there's nothing else to overlap it). `lag_probability(lag)` returns
`"high"` when the FLOD is the FVG itself (closer, tighter defense), `"low"` otherwise.

This three-tier language (FLOD/ODD/LOD) is MMC's vocabulary for "how many layers of
defense does price have to break through before this level truly fails," and it's the
axis the context layer (§11) and several of the strategies (§14) filter on directly.

**A known historical bug, and its current state:** `ANALYSIS.md` documents that an
earlier version of the pipeline never tagged any context area with `defense="ODD"` — a
detection bug in `find_context_areas` that made strategy S4 (ODD-filtered) produce zero
trades. The current `mmc/context/usual.py` contains an explicit code comment referencing
this exact bug and logic that does construct FVAs and tag `ODD` areas. This documentation
set does not claim that bug is proven fixed — re-running S4 to confirm a non-zero trade
count was out of scope for this pass — but the code today visibly contains the mechanism
the bug report says was missing. Document 4 states this precisely as an open item.

## 9. Sweeps — three independent lenses on "did this level actually fail"

MMC's `mmc.sweeps` package answers one recurring question — *"price broke a level; did it
reverse (a **sweep**, i.e. a liquidity grab / turtle-soup) or continue (a **run**)?"* —
from three different angles, each in its own module:

- **Liquidity sweep vs. run** (`mmc.sweeps.liquidity.classify_liquidity`) — after price
  breaks a swing level (`_break_index`), look forward `window` bars for the first FVG to
  form. An **opposing**-direction FVG within the window means the break was a genuine
  reversal (`LiquidityEvent.SWEEP`); a same-direction FVG or no FVG at all means price
  just kept running (`LiquidityEvent.RUN`).
- **Order flow sweep** (`mmc.sweeps.order_flow.order_flow_sweeps`) — a narrower,
  different pattern: for each *mitigated* FVG, find the opposing swing left behind near
  the mitigation point; if no *new* same-direction FVG forms within `window` bars after
  that swing, it's recorded as an `OrderFlowSweep` — a failed rejection.
- **Candle science sweep** (`mmc.sweeps.candle_science`) — the single-candle version:
  did the first candle to trade into a level actually reject it, using previous
  candle high/low (`previous_candle_high`/`previous_candle_low`) as the reference.

The package's own docstring calls these "two fractal lenses on a sweep" (order flow vs.
candle science) with liquidity classification as a third, coarser view. They are
deliberately kept as separate, independently testable functions rather than one combined
"is this a sweep" black box.

## 10. Candle science — single-candle respect/disrespect

`mmc.candle_science.classify.classify_candle(open, high, low, close,
respect_wick_ratio=0.5, body_ratio_floor=0.0)` classifies one candle as **respect**
(price rejected a level — the longest wick's ratio of the bar's full range exceeds the
threshold, and the implied direction is *away* from that long wick) or **disrespect**
(the body's own direction dominates, or, on a flat/doji body, whichever wick is smaller).
Degenerate zero-range candles are handled explicitly. This is deliberately the simplest,
most mechanical layer in the whole package — pure arithmetic over one bar's OHLC, no
history needed — which is exactly why it can sit in parallel with `narrative` and
`sweeps` rather than depending on either.

## 11. Kill zones — session timing

`mmc.timing.sessions` defines two `KillZone` session windows: `FOREX = 02:00–10:00`
(New York time) and `INDEX = 09:30–16:00`. `in_killzone()`/`killzone_window()` use
half-open interval containment (`.contains()`), and `to_newyork()` normalizes naive
timestamps as already-NY-local while converting tz-aware ones via `tz_convert`. The
methodology restricts *when* a setup is even considered valid — a textbook-perfect FVG
outside the relevant kill zone is treated differently from one that forms inside it.

## 12. Usual and unusual context — turning narrative into a tradeable zone

`mmc.context.usual.find_context_areas` is where FLOD/ODD/LOD narrative (§8) becomes a
concrete `ContextArea` (a zone with a `boundary`, `target`, `direction`, `kind`,
`defense` field). It also adds two more context flavors for swings that never got an FVG
at all: **LOD form (a)** — a bare swing with no lag — and **LOD form (b)** — a
previous-candle-sweep-based context, from `_lod_candle_science_contexts`.

`mmc.context.unusual.find_unusual_context` is the second, rarer pattern: for a lag whose
FVA `is_seeking_liquidity` (price later trades beyond the FVA's far edge —
`mmc.narrative.lag.is_seeking_liquidity`), it looks for the opposing FVG that formed
*inside* that FVA and emits a `kind="unusual"` context area targeting the FVA's far side.
"Usual" is the textbook FLOD/ODD/LOD progression; "unusual" is price ignoring the near
defense entirely and running straight for the area beyond it.

## 13. Entries — turning a context area into an order

`mmc.entry.detect.find_sharp_turns(context_area, entry_df, rr=2.0, fast_threshold=6)`
looks for an FVG *opposing* the context's direction that first touches the context
boundary, then a same-direction FVG that clears it — the entry sits on that second
("FVG-out") gap, with the stop from the anchoring lag's swing.
`find_order_flow_entries` is the second entry model: two same-direction lags inside the
same context area, entering on the second. Both build an `Entry` (`entry_zone`,
`stop_loss`, `take_profit`, `rr`, `entry_type`) via `mmc.entry.signal`:
`make_stop_loss(lag, direction, buffer=0.0)` places the stop at the lag's swing price;
`make_take_profit(entry_price, stop_loss, rr=2.0)` computes a fixed-RR target.
`Entry.entry_price` is the near edge of the anchoring FVG (a limit order, not
market — see §15).

## 14. Top-down bias

`mmc.topdown.bias.compute_bias(data_by_tf, ...)` gathers up to three **arguments** per
timeframe — one each from order flow, market structure, and candle science
(`_order_flow_argument`, `_market_structure_argument`, `_candle_science_argument`) — and
accumulates bullish/bearish counts across timeframes into a `Bias` (`direction`,
`n_bullish`, `n_bearish`, `confidence` = winning-side args / total args, `one_sided` =
true only when every argument agrees *and* there are at least `one_sided_min_args`
of them). `mmc.strategies` uses this (`best_pair`, `TraderStyle.FILTERING_PROCESS`) to
pick which pair and directional bias to trade in strategy S1.

## 15. Event-driven backtesting

MMC's backtester (`mmc.backtest`) does not simulate every bar against every possible
signal at once — it replays a fixed list of already-detected `Entry` objects
bar-by-bar, in order, which is what "event-driven" means here (as opposed to a
vectorized, whole-array backtest). `mmc.backtest.fill.simulate_entry(entry, df,
max_hold=None)`:

1. From `entry.index + 1` onward, waits for price to touch the **limit** entry price —
   if it never does, the trade is `Outcome.NO_FILL`.
2. From the fill bar onward, checks stop-loss and take-profit each bar. **If a single
   bar's range would hit both levels, the simulation conservatively assumes the stop was
   hit first** and marks the trade `ambiguous=True` — this is a deliberate, documented
   design choice (design decision #3 in document 2), not an oversight, because OHLC bars
   don't tell you the intrabar path.
3. If `max_hold` bars pass with neither hit, the trade exits at that bar's close as
   `Outcome.TIMEOUT`.

Results are expressed in **R-multiples** — P&L as a multiple of the amount risked (a
`take_profit` at `rr=2.0` means "risk 1R to make 2R"), not in currency, which is what
lets `BacktestResult` (`win_rate`, `expectancy`, `profit_factor`, `average_rr`,
`max_consecutive_losses`, `.equity_curve`) stay symbol- and position-size-agnostic.

## 16. Layered, dependency-ordered package design

MMC is `pip install`-able (`pyproject.toml`: `[tool.setuptools.packages.find] include =
["mmc*"]`) and its subpackages are arranged so that each one only imports from layers
strictly below it — verified directly against import statements, not just the
architecture doc's table:

```
mmc.data                         (no mmc deps)
mmc.core                         (no mmc deps beyond mmc.data's DataFrame contract)
mmc.narrative, mmc.sweeps,       (each imports only mmc.core)
mmc.candle_science, mmc.timing
mmc.context                      (imports mmc.core + mmc.narrative + mmc.sweeps)
mmc.entry                        (imports mmc.core + mmc.context + mmc.timing)
mmc.topdown                      (imports everything above)
mmc.backtest                     (imports only mmc.entry's Entry type)
```

This is why document 2 can trace one call chain end to end without ever finding a
layer reaching "sideways" or "up" — `ARCHITECTURE.md`'s stated rule ("stay inside your
module") is actually enforced by what the code imports, not just documented as a
convention.

## 17. The neural-network subsystem — what's real and what isn't yet verified

`mmc/brain/` is a genuine, separately-maintained PyTorch subsystem (real
`import torch; import torch.nn as nn`, three real architectures — `Perceptron`,
`ShallowNN`, `DeepNN` — real trained `.pt` weight files on disk per symbol × timeframe
combo × variant, plus MT5 live-fleet robot logs proving it has actually been run against
live data). It is **not** aspirational or unused scaffolding. Two honest caveats,
though:

- It is **not covered by the pytest suite** — `grep -rln "mmc.brain" tests/` returns
  nothing.
- `torch` is **not declared** in `pyproject.toml`'s `dependencies` (only `pandas` and
  `numpy` are) — so the documented install path, `pip install -e .`, will not pull in
  what `mmc.brain` needs. It sits functionally outside the officially packaged contract
  the "pip-installable library" resume claim describes.

On the specific confidence numbers (FLOD 65% / ODD 78% / Unusual 88%) quoted in both
`NEURAL_NETWORK_GUIDE.md` and `ANALYSIS.md`: this study set did not independently
re-run a trained model to reproduce those exact figures from raw output — they are
presented in the source docs as the methodology's own stated confidence hierarchy, and
should be described to an interviewer as *documented*, not as numbers this session
freshly measured. See document 4 for the fully scripted, honest answer.

## 18. Glossary

- **Candle science** — single-candle respect/disrespect classification by wick/body ratio.
- **Context area** — a tradeable zone (`ContextArea`) built from a decomposed order flow
  lag, tagged `usual`/`unusual` and `FLOD`/`ODD`/`LOD`.
- **Direction (Bullish/Bearish)** — `Direction` enum; bullish = discount/buy array,
  bearish = premium/sell array.
- **Entry** — a concrete limit order (`Entry`) with entry zone, stop, target, RR.
- **Event-driven backtest** — replays a fixed ordered list of `Entry` events bar-by-bar,
  as opposed to a vectorized whole-array simulation.
- **Fair Value Area (FVA)** — the zone between two opposing structure points (ITH/ITL).
- **Fair Value Gap (FVG)** — a 3-candle imbalance/gap pattern.
- **FLOD** — First Line Of Defense: whichever boundary (FVG or FVA) price retraces into
  first.
- **ITH/ITL** — Intermediate-Term High/Low: a swing lower/higher than its same-type
  neighbors.
- **Kill zone** — a session time window (`KillZone.FOREX`, `KillZone.INDEX`) during which
  setups are considered valid.
- **LOD** — Last Line Of Defense: always the raw swing point itself.
- **Liquidity run** — price breaks a level and keeps going (no opposing FVG within
  window).
- **Liquidity sweep** — price breaks a level and reverses (opposing FVG within window).
- **ODD** — Overlapping Defense: whichever of FVG/FVA is not the FLOD.
- **Order flow lag** — an `OrderFlowLag`: a swing paired with its confirming FVG; the
  central object of the whole codebase.
- **Order flow sweep** — a swing left behind after a mitigated FVG's failed rejection,
  distinct from a liquidity sweep.
- **Polarity** — bullish=discount=buy array (swing low); bearish=premium=sell array
  (swing high).
- **PD array** — premium/discount array; a price zone the methodology expects to be
  defended.
- **R-multiple** — P&L expressed as a multiple of risk (1R = the amount risked).
- **RR (risk:reward)** — ratio of target distance to stop distance for an entry.
- **STH/STL** — Short-Term High/Low: a swing confirmed by an opposing FVG within a small
  window.
- **Swing point** — a 3-bar fractal high or low; the most primitive detected structure.
- **Top-down bias** — cross-timeframe directional confidence accumulated from order
  flow, market structure, and candle science arguments.
- **Zone** — the base dataclass (`top`, `bottom`, `direction`) that `FairValueGap` and
  `FairValueArea` both extend.

---

## Self-test

**Level 1.** Define, in order: swing point, FVG, ITH/ITL, STH/STL, FVA, order flow lag.
State the bullish/bearish polarity convention for a swing high vs. a swing low.

**Level 2.** Why does an STH require an *opposing* FVG rather than a same-direction one?
Why does `mmc.backtest` only ever import `mmc.entry`, never `mmc.core` directly?

**Level 3.** *"Isn't 'liquidity sweep' and 'order flow sweep' just the same thing twice?"*
Answer using §9: no — they're independently computed from different evidence
(`classify_liquidity` looks at whether an *opposing* FVG forms after a *swing break*;
`order_flow_sweeps` looks at whether a *new same-direction* FVG forms after a swing left
behind by a *mitigated* FVG's failed rejection) and live in separate, separately-tested
modules — `mmc/sweeps/liquidity.py` and `mmc/sweeps/order_flow.py` — on purpose, per the
package's own "two fractal lenses" docstring.

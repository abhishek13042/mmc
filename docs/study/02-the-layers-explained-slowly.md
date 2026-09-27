# Study Guide 2 — The layers, explained slowly

This document traces one real, reproducible run through every layer of the real
`mmc/` package, in dependency order, using real file paths and function names. The run:

```
python examples/run_backtest.py EURUSD H1 2000
```

Real output, captured in this session:

```
Backtesting EURUSD H1 (last 2000 bars)...

MMC backtest result
-------------------
signals processed : 898
trades (filled)   : 836
no-fills          : 62
wins / losses     : 370 / 466
timeouts          : 0
win rate          : 44.3%
expectancy (R)    : +0.328
total (R)         : +274.000
average RR        : 2.00
profit factor     : 1.59
max consec losses : 88
```

`examples/run_backtest.py` is a thin CLI wrapper (`SYMBOL TIMEFRAME LIMIT`, defaulting to
`EURUSD H1 2000`) around one function: `mmc.backtest.engine.backtest_symbol`. Everything
below is what that one call actually does.

## The whole flow, one page

```
 mmc_backtest/data/raw/EURUSD_H1.csv
              │
              ▼
 mmc.data.loader.load("EURUSD", Timeframe.H1)
              │  DataFrame: DatetimeIndex, float OHLC, df.attrs["symbol"/"timeframe"]
              ▼
 mmc.core.structure.analyze(df, window=3)
    ├─ find_swings(df)                  → list[SwingPoint]
    ├─ find_fvgs(df) + mark_mitigation  → list[FairValueGap]
    ├─ intermediate_term_points(swings) → list[StructurePoint]  (ITH/ITL)
    ├─ short_term_points(swings, fvgs)  → list[StructurePoint]  (STH/STL)
    ├─ fair_value_areas(structure pts)  → list[FairValueArea]
    └─ find_order_flow_lags(swings,fvgs)→ list[OrderFlowLag]        ◄── central object
              │
              ▼
 mmc.narrative.lag.decompose_lag(lag, df, fvas)   for each OrderFlowLag
    sets lag.lod = lag.swing (always)
    attaches nearest overlapping FVA if lag.fva is unset
    picks whichever of FVG / FVA price would retrace into first → lag.flod
    the other becomes                                            → lag.odd
              │
              ▼         (in parallel, same OrderFlowLag / swing / fvg inputs)
 mmc.sweeps.liquidity.classify_liquidity   → SWEEP or RUN per broken swing
 mmc.sweeps.order_flow.order_flow_sweeps   → OrderFlowSweep list (failed rejections)
 mmc.candle_science.classify.classify_candle → respect/disrespect per bar
 mmc.timing.sessions.in_killzone           → is this bar's session valid?
              │
              ▼
 mmc.context.usual.find_context_areas(df, swings, fvgs, fvas)
    decomposes each lag → emits ContextArea(kind="usual", defense="FLOD"/"ODD")
    + _lod_swing_contexts()          (LOD form a: bare swing, no FVG)
    + _lod_candle_science_contexts() (LOD form b: previous-candle sweep)
 mmc.context.unusual.find_unusual_context(df, ...)
    lag.fva.is_seeking_liquidity → ContextArea(kind="unusual", defense="LOD")
              │
              ▼
 mmc.entry.detect.find_sharp_turns(context_area, entry_df, rr=2.0)
    opposing FVG touches boundary → same-direction FVG clears it → entry on FVG-out
 mmc.entry.detect.find_order_flow_entries(context_area, entry_df, rr=2.0)
    two same-direction lags inside context → entry on the second
      │  mmc.entry.signal.make_stop_loss(lag, direction)   → stop = lag.swing.price
      │  mmc.entry.signal.make_take_profit(entry, stop, rr)→ target at fixed RR
              ▼
 list[Entry]            (entry_zone, stop_loss, take_profit, rr=2.0, index)
              │
              ▼
 mmc.backtest.engine.run_backtest(entries, df)
    per entry: mmc.backtest.fill.simulate_entry(entry, df, max_hold)
      1. wait for price to touch the limit entry price     → else NO_FILL
      2. from fill bar, check SL/TP each bar
         both hit same bar → assume STOP first, ambiguous=True   [decision #3]
      3. max_hold exceeded, neither hit → TIMEOUT at bar close
              │
              ▼
 mmc.backtest.result.BacktestResult(trades=[...])
    .win_rate .expectancy .total_r .profit_factor .max_consecutive_losses .equity_curve
              │
              ▼
        "MMC backtest result" summary printed above
```

## Step by step, with the real captured numbers

### 1. `mmc.data.loader.load("EURUSD", Timeframe.H1)`

Reads `mmc_backtest/data/raw/EURUSD_H1.<ext>` — a tab-separated, headerless CSV — sorts
it into a `DatetimeIndex`, coerces OHLC to `float`, and stamps
`df.attrs["symbol"]="EURUSD"`, `df.attrs["timeframe"]=Timeframe.H1`. `limit=2000` in
`backtest_symbol` caps this to the last 2000 bars before anything downstream runs, purely
for speed.

**Design decision #1 — integer positional indexing everywhere.** Every downstream object
(`SwingPoint.index`, `FairValueGap.c1_index`, `Entry.index`) is a plain Python `int`
positional offset into this DataFrame, not a timestamp. `ARCHITECTURE.md` states this as
a hard contract. The payoff: comparing "is bar A before bar B" downstream is a plain
integer comparison, not a timestamp-arithmetic problem — but it does mean every object is
only meaningful paired with the exact DataFrame it was built from.

### 2. `mmc.core.structure.analyze(df, window=3)`

This single call runs the entire `mmc.core` detection pipeline and is the one function
document 1 §7 describes. On the 2000-bar EURUSD H1 window it produces the full set of
swings, FVGs, ITH/ITL, STH/STL, FVAs, and — the object everything downstream actually
consumes — `order_flow_lags`.

**Design decision #2 — polarity is baked into the type, not re-derived per caller.**
`SwingPoint.direction`, `Zone.is_premium`/`is_discount` compute polarity once, at
construction, from the swing/zone kind — every later layer (narrative, context, entry)
reads `.direction` rather than re-implementing "is this bullish or bearish" from raw
price. This is why the same polarity convention (bullish=discount=swing low,
bearish=premium=swing high) holds identically in every layer without drift.

### 3. `mmc.narrative.lag.decompose_lag` — narrative per lag

For each `OrderFlowLag` from step 2, `decompose_lag` sets `lag.lod = lag.swing` (always),
attaches the nearest overlapping FVA if the lag doesn't already have one, and — only if
an FVA is present — decides which of the FVG or FVA price would retrace into first
(`_retrace_first`), making that the `FLOD` and the other the `ODD`. With no FVA, the FVG
is both. This is pure geometry over already-detected zones — no new price scanning here.

### 4. Sweeps and candle science — parallel, independent classifications

`mmc.sweeps.liquidity.classify_liquidity`, `mmc.sweeps.order_flow.order_flow_sweeps`, and
`mmc.candle_science.classify.classify_candle` all run over the same swing/FVG/bar data
but **do not feed each other** — they're three independent lenses (document 1 §9) that
the context layer (step 5) consults separately when deciding whether a context area is
"usual" or worth a candle-science-based LOD tag.

### 5. `mmc.context.usual.find_context_areas` + `mmc.context.unusual.find_unusual_context`

Turns decomposed lags into `ContextArea` objects — the first concrete "here is a
tradeable zone" object in the pipeline. `find_context_areas` builds its own FVAs
internally if none are supplied, with a code comment explicitly citing the historical
"S4 ODD zero trades" bug from `ANALYSIS.md` (document 1 §8, document 4 discuss this in
full) as the reason that step must not be skipped.

### 6. `mmc.entry.detect.find_sharp_turns` / `find_order_flow_entries`

Both consume `ContextArea` objects and `entry_df` (the entry timeframe's bars) and emit
`Entry` objects via `mmc.entry.signal.make_stop_loss`/`make_take_profit`. In this example
run, `rr=2.0` is the default, matching the printed `average RR: 2.00`.

**Design decision #3 — the entry price is a limit, not a market fill.**
`Entry.entry_price` is the *near edge* of the anchoring FVG — the backtester's
`simulate_entry` explicitly waits for price to trade back to that level before
considering the trade filled at all. This is why the printed summary shows **62 no-fills
out of 898 signals processed** — roughly 7% of detected setups never actually got touched
by price in this window, and the backtester counts that honestly instead of assuming
every signal fills.

### 7. `mmc.backtest.fill.simulate_entry` — the deterministic core

For each of the 836 filled trades: walk forward bar by bar from the fill point, checking
stop and target each bar.

**Design decision #4 — same-bar SL/TP ambiguity resolved conservatively.** If a single
bar's high/low range would touch both the stop and the target, `simulate_entry` assumes
the **stop hit first** and marks `Trade.ambiguous=True`. OHLC bars carry no intrabar path
information, so this can't be resolved exactly — the conservative choice deliberately
understates performance rather than flattering it. This is the single most important
methodological choice in the whole backtester to be able to defend under questioning
(see document 4).

**Design decision #5 — `max_hold` timeout exits at bar close, not at a level.** A trade
that never resolves within `max_hold` bars exits at that bar's raw close price as
`Outcome.TIMEOUT`. In this particular run, `timeouts: 0` — every one of the 836 filled
trades resolved to a win or loss within the window, none aged out.

### 8. `mmc.backtest.result.BacktestResult` — the summary

`win_rate = wins / filled_trades = 370/836 = 44.3%`; `expectancy` is the mean R per
trade (`+0.328R`); `total_r = +274.000` is the raw sum (also `expectancy × filled_trades
≈ 0.328 × 836 ≈ 274`, consistent); `profit_factor = gross_profit / gross_loss = 1.59`;
`max_consecutive_losses = 88` is read directly off the trade sequence, not smoothed.

**Design decision #6 — a 44% win rate with a positive total R is not a contradiction.**
At a fixed 2R target, break-even win rate is 1/(1+2) ≈ 33.3%. 44.3% sits comfortably
above that, which is exactly why `total_r` and `profit_factor` are both positive despite
losses outnumbering wins (466 vs. 370) — the RR structure, not the win rate, carries the
edge. This is a fact worth having ready cold: an interviewer who sees "44% win rate" and
assumes "losing system" without checking RR is testing whether you understand your own
numbers.

## Where `mmc.topdown` fits (not exercised by this particular example)

`examples/run_backtest.py`'s call to `backtest_symbol` does not invoke
`mmc.topdown.bias.compute_bias` — that layer is consumed separately by
`mmc.strategies.s1_filtering_process`, which calls `mmc.topdown.best_pair` to pick a pair
and directional bias *before* filtering context areas, rather than being part of the
core single-symbol backtest path shown above. It's real, tested code (7 tests in
`tests/test_topdown.py`), just not on the specific call path this example traced — say so
plainly if asked rather than implying it ran here.

---

## Self-test

**Level 1.** Name, in order, the nine real function/module calls this document traces
from raw CSV to `BacktestResult`. State the six numbered design decisions in one
sentence each.

**Level 2.** Why does `simulate_entry` wait for a limit touch before considering a trade
"open," rather than assuming an immediate market fill at `Entry.index`? What real number
in the captured run is direct evidence this matters?

**Level 3.** *"Your example backtest shows more losses than wins — how is that a working
strategy?"* Answer using design decision #6: 466 losses vs. 370 wins is a 44.3% win rate,
which clears the ~33.3% break-even threshold for a fixed 2R target — the edge lives in
the reward:risk structure (every winner pays 2R, every loser costs 1R), not in winning
more often than losing, and `total_r=+274` / `profit_factor=1.59` are the direct
arithmetic consequence, not a separate claim.

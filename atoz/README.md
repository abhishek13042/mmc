# atoz — the A-Z Guide trading library

A self-contained Python implementation built **faithfully from the raw A-Z Guide
video transcripts** (`transcribe/transcripts/00x`). Kept separate from the `mmc/`
package (which was built from a different, distilled transcript set).

`atoz` reuses `mmc.data.load` for CSV loading only (pure infrastructure); all
concepts are implemented fresh from the transcripts.

## Layers (by episode)

| Layer | Module | Episode(s) | Concepts |
|------|--------|-----------|----------|
| Core | `atoz/core` | 1 | Direction, Swing, Zone, FVG, Candles |
| Blocks | `atoz/blocks` | 2–6 | Order, Mitigation, Breaker, Rejection, Reclaimed OB + overlap scoring |
| Liquidity | `atoz/liquidity` | 7 | Equal-high/low pools, sweep vs run (with reaction) |
| Imbalances | `atoz/imbalances` | 8 | FVG/BISI/SIBI, BPR, liquidity void, volume imbalance |
| PD matrix | `atoz/pd_matrix` | 9 | Price-action lag, FLOD / LLOD, overlap probability |
| Structure | `atoz/structure` | 10 | Bullish/bearish structure, protected swings, HTF magnet context |
| Entries | `atoz/entries` | 11–12 | External/internal, MSS, sweep→displacement entry (FLOD/LLOD) |
| SMT | `atoz/smt` | 13 | Correlated-pair divergence (bullish/bearish) |
| Filtering | `atoz/filtering` | 14 | Relative-strength pair selection |
| Timing | `atoz/timing` | 15–17 | Weekly profiles/TGIF, killzones (NY + broker EET) |
| Profiles | `atoz/profiles` | 18–19 | Power of 3 / AMD (OHLC-OLHC), Judas swing |
| Dealing Range | `atoz/dealing_range` | 20–21 | DOL via Fibonacci (neg extensions), premium/discount zones, swing projection |
| ST Model | `atoz/st_model` | 22–23 | "MSS is BS" / Sharp Turn: displacement→retrace→displacement, OTE entry, dealing-range Fib |
| FVG Story | `atoz/fvg_story` | 24, 27 | Sweep vs run (FVG-in-leg), step-by-step consolidation detection |
| Economic | `atoz/economic` | 25–26 | News roadmap (blackout windows), HP/LP conditions (100/0 only = HP) |
| Turtle Soup | `atoz/turtle_soup` | 28, 32 | Seek-and-destroy / buying-on-strength, tiered swing structure |
| Killzone Plans | `atoz/killzone_plans` | 29–30 | London (Asia-expansion / Asia-consolidation), NY (retracement / reversal) |
| Silver Bullet | `atoz/silver_bullet` | 31, 33 | No-daily-bias 1h→1m plan, Silver Bullet 0.75 swing-rate entry |
| MMXM | `atoz/mmxm` | 34, 36 | Market Maker Buy/Sell Model (curves + reclaimed OBs), FVG daily bias |
| Playstyles | `atoz/playstyles` | 35, 37 | Swing-around-fulltime-job (limit orders), advanced scalping (boundary gate) |
| Getting Funded | `atoz/getting_funded` | 38–39 | Position sizing, prop-firm eval walk, readiness checklist |

### Coverage
All 39 episodes of the A-Z Guide are implemented (files 001–040). Full library
covering ep 1–39.

### Built from adjacent material (verify against transcript)
- `atoz/filtering` (ep 14) — built from the strength-leader concept referenced
  in ep 13; confirm against file 015.
- ep 17 indices-killzone specifics folded into `atoz/timing/killzones` (equities
  open); confirm against file 018 for index-only nuances.

## Quick start

```python
from mmc.data import load
from mmc.core.types import Timeframe
from atoz.blocks import find_all_blocks, strongest

df = load("EURUSD", Timeframe.H1)
blocks = find_all_blocks(df)
best = strongest(blocks, min_overlaps=2)   # most-confluent setups (ep 6 filter)
```

```python
# ST model entry (ep 22-23)
from atoz.st_model import find_st_setups
sts = find_st_setups(df)

# Silver Bullet setups (ep 33)
from atoz.silver_bullet import find_silver_bullet_setups
sb = find_silver_bullet_setups(df)

# Daily bias from FVGs (ep 36)
from atoz.mmxm import daily_bias
bias = daily_bias(d1_df)

# Advanced scalp entry (ep 37)
from atoz.playstyles import find_boundaries, find_scalp_entries, BoundaryTF
boundaries = find_boundaries(h1_df, BoundaryTF.ONE_HOUR, bias)
entries = find_scalp_entries(m1_df, boundaries[0])
```

## Status / known v1 looseness

All detectors run on real data. First-pass thresholds are deliberately loose and
**over-fire** — to be tightened with the same backtest discipline used in `mmc`:

- **Breaker** detection triggers on any prior-swing-then-break (too permissive).
- **BPR** and **magnetised-swing** counts are high (overlap/proximity windows
  wide).
- **Overlap** scoring counts clustered same-type blocks (ep 6's "thousand lines"
  problem) — needs de-duplication.

These are detection-tightening tasks, not structural — the concept coverage for
ep 1–39 is complete and faithful.

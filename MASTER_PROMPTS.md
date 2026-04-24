# MMC Arjo Strategy Reset — Master Prompt Collection

> **READ THIS FIRST:** These prompts are ordered sequentially. Run them one by one in a new chat. Do NOT skip any prompt. Do NOT mix prompts.

---

## WHAT ARJO ACTUALLY TAUGHT — STRATEGIES EXTRACTED FROM VIDEO TRANSLATIONS

After deeply reading all 12 video translation files (video1_pd_arrays.py through video12_top_down.py), here is the **COMPLETE and EXACT list of strategies Arjo shared**. There are **NOT 25 strategies**. Arjo shared **7 core repeatable trading setups**, each with specific conditions:

### Arjo's 7 Confirmed Strategies (From Videos):

1. **OFL Continuation** — Enter on a PFVG inside a High-Probability Order Flow Level (OFL). Requires: PFVG + FLOD + OFL DIRECTION alignment + no opposing PDA blocking. Entry at FVG low (BULLISH) or FVG high (BEARISH). SL below/above OFL swing point. TP = 2R minimum.

2. **FVA Ideal Setup (Triple Probability)** — Enter from an IDEAL Fair Value Area (FVA). Requires: FVA has overlapping PFVG + has nested inner FVA + no sweep. Enter from nested FVA boundary. SL at FVA low/high. TP = nearest structural target (IT_HIGH / IT_LOW / BSL / SSL).

3. **FVA Good Setup (Double Probability)** — Enter from a GOOD FVA. Requires: FVA has overlapping FVG (PFVG or BFVG) but no nested FVA. No sweep. Enter at FVA + FVG overlap zone. SL at OFL swing. TP = 2R.

4. **Sweep + OFL (Order Flow Sweep / MSS)** — Enter after a liquidity sweep of a swing point followed by a continuation FVG. Requires: Sweep event (wicked beyond swing, closed back), continuation FVG in direction, OFL present. Enter at continuation FVG. SL below/above sweep wick low/high. TP = 2R minimum.

5. **Candle Science Bias Entry** — Identify DISRESPECT or RESPECT candle on D1/W1/M1 timeframe. Enter on lower TF in direction of candle science. Requires: Candle science candle + lower TF OFL alignment + in killzone. Enter at lower TF FVG. SL at lower TF OFL swing. TP = 2R.

6. **Sharp Turn Entry (from Video 11)** — Enter when price enters context area and forms a Sharp Turn pattern (FVG_in then FVG_out forms). Requires: Active context area + FVG_in + FVG_out + OFL in entry TF. SL = most recent OFL swing. TP = context target.

7. **Order Flow Entry (from Video 11)** — Enter using two sequential OFLs on entry timeframe inside an active context area. Requires: Two OFLs same direction + context area active + entry TF validation pass. SL = OFL 2 swing point. TP = context target.

---

# PROMPT 0 — CLEANUP: Delete All Non-Essential Code

```
You are working inside the MMC Trading project located at:
  c:\Users\Admin\OneDrive\Desktop\MMC\mmc_backtest\

YOUR TASK: Delete all files and folders EXCEPT the following files which are
the video transcript translations (keep these EXACTLY as-is, zero modifications):

KEEP (do NOT touch these files):
  mmc_backtest/modules/video1_pd_arrays.py
  mmc_backtest/modules/video2_market_structure.py
  mmc_backtest/modules/video3_4_order_flow.py
  mmc_backtest/modules/video5_candle_science.py
  mmc_backtest/modules/video6_fvg_types.py
  mmc_backtest/modules/video7_fva_types.py
  mmc_backtest/modules/video8_sweeps.py
  mmc_backtest/modules/video9_time.py
  mmc_backtest/modules/video10_context.py
  mmc_backtest/modules/video11_entries.py
  mmc_backtest/modules/video12_top_down.py
  mmc_backtest/modules/__init__.py
  mmc_backtest/modules/data_engine.py   <- KEEP this too (data loading utility)

DELETE COMPLETELY (entire folders and all their contents):
  mmc_backtest/strategies/             <- DELETE entire folder
  mmc_backtest/routes/                 <- DELETE entire folder
  mmc_backtest/backtest/               <- DELETE entire folder
  mmc_backtest/frontend/src/           <- DELETE entire folder
  mmc_backtest/tests/                  <- DELETE entire folder
  mmc_backtest/scripts/                <- DELETE entire folder
  mmc_backtest/notebooks/              <- DELETE entire folder (we replace with Colab)
  mmc_backtest/static/                 <- DELETE entire folder
  mmc_backtest/templates/              <- DELETE entire folder

DELETE THESE FILES:
  mmc_backtest/app.py
  mmc_backtest/run.py
  mmc_backtest/run_step_6.py
  mmc_backtest/run_step_7.py
  mmc_backtest/batch_run_strategies.py
  mmc_backtest/batch_log.txt
  mmc_backtest/update_notebooks.py
  mmc_backtest/mmc_system.log
  mmc_backtest/config.py
  mmc_backtest/.env
  mmc_backtest/requirements.txt

CREATE THIS NEW FOLDER STRUCTURE (empty for now):
  mmc_backtest/
    modules/              <- already exists (keep)
    strategies/
      strategy_1_ofl_continuation/
      strategy_2_fva_ideal/
      strategy_3_fva_good/
      strategy_4_sweep_ofl/
      strategy_5_candle_science/
      strategy_6_sharp_turn/
      strategy_7_order_flow_entry/
    backtest/
      results/
    data/
      raw/
    colab/
    requirements.txt      <- create new minimal one

Create requirements.txt with:
  pandas>=2.0.0
  numpy>=1.24.0
  matplotlib>=3.7.0
  plotly>=5.0.0
  yfinance>=0.2.0

Do NOT create any Python files yet. Just the clean folder structure.
After you are done, print the final folder tree so I can verify.
```

---

# PROMPT 1 — DATA ENGINE (Prerequisite for all strategies)

```
You are rebuilding the MMC Trading Backtest System from scratch.

CONTEXT:
The folder is at: c:\Users\Admin\OneDrive\Desktop\MMC\mmc_backtest\
The modules/ folder contains 12 video translation files that define the complete
MMC methodology taught by Arjo. These are the GROUND TRUTH. Do not modify them.

YOUR TASK: Create mmc_backtest/backtest/data_loader.py

This file provides a clean, standalone data loader that:
1. Loads MT5-exported CSV files from mmc_backtest/data/raw/
2. MT5 CSV format: <DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<TICKVOL>,<VOL>,<SPREAD>
   Example filename: EURUSD_D1.csv, GBPUSD_H4.csv, XAUUSD_M15.csv
3. Parses datetime from <DATE> + <TIME> combined -> 'datetime' column as string "YYYY-MM-DD HH:MM:SS"
4. Returns DataFrame with columns: datetime, open, high, low, close (lowercase)
5. Filters out weekends (Saturday, Sunday)
6. Sorts by datetime ascending

FUNCTION SIGNATURES (exact):

def load_csv(filepath: str) -> pd.DataFrame:
    """
    Load a single MT5 CSV file. Returns clean DataFrame.
    Raises FileNotFoundError if file not found.
    Raises ValueError if columns don't match MT5 format.
    """

def get_available_data(data_dir: str) -> dict:
    """
    Scan data_dir for all CSV files.
    Returns dict like: {'EURUSD': ['D1', 'H4', 'M15'], 'GBPUSD': [...], ...}
    """

def fetch_candles(instrument: str, timeframe: str, data_dir: str = None) -> pd.DataFrame:
    """
    Load data for instrument + timeframe.
    instrument: 'EURUSD', 'GBPUSD', 'XAUUSD'
    timeframe: 'DAILY', '4H', '1H', '15M', '5M', '1M', 'WEEKLY', 'MONTHLY'
    Timeframe to filename mapping:
      'DAILY'   -> 'D1'
      '4H'      -> 'H4'
      '1H'      -> 'H1'
      '15M'     -> 'M15'
      '5M'      -> 'M5'
      '1M'      -> 'M1'
      'WEEKLY'  -> 'W1'
      'MONTHLY' -> 'MN1'
    Default data_dir = mmc_backtest/data/raw/ (relative to this file)
    Raises FileNotFoundError with clear message listing which file it looked for.
    Returns sorted, filtered DataFrame.
    """

IMPORTANT:
- Use only pandas and os. No Flask, no SQLAlchemy, no database.
- Every function must have full error handling with descriptive messages.
- Add a __main__ block that tests loading EURUSD D1 if available.
- Print clear success/error messages.

Also create mmc_backtest/backtest/__init__.py (empty).
Also create mmc_backtest/strategies/__init__.py (empty).

After creating, print the full file contents so I can verify.
```

---

# PROMPT 2 — STRATEGY 1: OFL Continuation Backtest

```
You are implementing Strategy 1 of 7 for the MMC Trading System.
This strategy was explicitly taught by Arjo in Videos 1-4 of the MMC course.

FOLDER: mmc_backtest/strategies/strategy_1_ofl_continuation/
FILES TO CREATE:
  __init__.py       (empty)
  scanner.py        (signal detection)
  backtest.py       (full backtest runner)
  visualize.py      (charts and plots)

STRATEGY 1: OFL CONTINUATION — Complete Rules from Arjo

PURPOSE: Enter in the direction of a High Probability Order Flow Level (OFL).

ARJO'S EXACT CONDITIONS (all must be TRUE to take entry):

CONDITION 1 - PFVG Must Exist (from video1_pd_arrays.py logic):
  - Scan candles for FVGs using scan_candles_for_fvgs(df, instrument)
  - Filter: fvg_type == 'PFVG' (rejection_ratio < 0.25)
  - Filter: is_mitigated == False
  - At least one PFVG must exist in your working timeframe

CONDITION 2 - OFL Must Be High Probability (from video3_4_order_flow.py):
  - Call full_order_flow_scan(instrument, timeframe)
  - most_recent_ofl must NOT be None
  - most_recent_ofl['probability_label'] must == 'HIGH'
  - most_recent_ofl['is_confirmed'] must == True

CONDITION 3 - Direction Alignment:
  - OFL direction and PFVG direction must match
  - BULLISH: OFL direction == 'BULLISH' AND PFVG direction == 'BULLISH'
  - BEARISH: OFL direction == 'BEARISH' AND PFVG direction == 'BEARISH'

CONDITION 4 - No Opposing PDA Blocking the Path:
  - After entry, check if any UNMITIGATED opposing PDA exists before the TP target
  - BULLISH: scan for unmitigated BEARISH FVGs and SWING_HIGHs above entry price
  - BEARISH: scan for unmitigated BULLISH FVGs and SWING_LOWs below entry price
  - If any blocking PDA exists closer than the TP target: SKIP TRADE

ENTRY RULES:
  - BULLISH: entry_price = PFVG fvg_low (enter at bottom of bullish gap)
  - BEARISH: entry_price = PFVG fvg_high (enter at top of bearish gap)

STOP LOSS RULES (EXACT from Arjo):
  - Get the OFL swing_point_price
  - Buffer: 2 pips for EURUSD/GBPUSD (0.0002), 20 pips for XAUUSD (0.20)
  - BULLISH: stop_loss = ofl_swing_point_price - buffer_in_price
  - BEARISH: stop_loss = ofl_swing_point_price + buffer_in_price
  - If risk <= 0: SKIP (invalid setup)

TAKE PROFIT RULES:
  - risk = abs(entry_price - stop_loss)
  - tp_1R = entry +/- risk * 1.0
  - tp_2R = entry +/- risk * 2.0  <- MINIMUM TARGET
  - tp_4R = entry +/- risk * 4.0
  - Find nearest structural target using scan_it_points() for IT_HIGH (bull) or IT_LOW (bear)
  - If structural target is closer than tp_2R: SKIP TRADE (not enough room)

FILE: scanner.py

Import setup (add at top of each scanner file):
  import sys, os
  sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
  from mmc_backtest.modules.video1_pd_arrays import scan_candles_for_fvgs, scan_candles_for_swings, get_pip_multiplier
  from mmc_backtest.modules.video2_market_structure import scan_it_points
  from mmc_backtest.modules.video3_4_order_flow import scan_candles_for_ofls
  from mmc_backtest.modules.video6_fvg_types import scan_and_classify_all_fvgs
  from mmc_backtest.backtest.data_loader import fetch_candles

FUNCTION: scan_ofl_continuation(df, instrument, timeframe) -> list[dict]
  Use rolling window: for each candle position i, use df.iloc[:i] to simulate real-time.
  Minimum window = 50 candles.

  Each signal dict must contain:
  {
    'strategy': 'OFL_CONTINUATION',
    'instrument': instrument,
    'timeframe': timeframe,
    'signal_datetime': str,
    'direction': 'BULLISH' or 'BEARISH',
    'entry_price': float,
    'stop_loss': float,
    'tp_1r': float,
    'tp_2r': float,
    'tp_4r': float,
    'risk_pips': float,
    'pfvg_high': float,
    'pfvg_low': float,
    'ofl_probability': str,
    'ofl_swing_price': float,
    'path_is_clear': bool,
    'conditions_met': list[str],
  }

FILE: backtest.py

FUNCTION: run_backtest(instrument, timeframe, data_dir=None) -> dict

Steps:
  1. Load full historical data using fetch_candles(instrument, timeframe, data_dir)
  2. Scan for all signals using scanner.scan_ofl_continuation(df, instrument, timeframe)
  3. For each signal, simulate trade outcome by walking forward candle by candle:
     - If candle low <= stop_loss: result = 'LOSS', rr_achieved = -1.0
     - If candle high >= tp_2r (bull) or candle low <= tp_2r (bear): result = 'WIN', rr_achieved = 2.0
     - If candle high >= tp_4r after tp_2r: update rr_achieved = 4.0
     - If 100 candles pass without hit: result = 'NEUTRAL', rr_achieved = 0.0
  4. Calculate statistics:
     total_signals, wins, losses, neutrals,
     win_rate_pct, total_rr, avg_rr, max_consecutive_losses,
     best_trade_rr, worst_trade_rr
  5. Return full results dict including all trade details

FUNCTION: save_results(results_dict, output_path) -> None
  Save to JSON file at output_path.

FILE: visualize.py

FUNCTION: plot_equity_curve(results_dict, save_path=None)
  Plot cumulative RR over trade number using matplotlib.
  Title: "Strategy 1 - OFL Continuation | {instrument} {timeframe}"
  Green line for equity, horizontal zero line, drawdown shading.

FUNCTION: plot_win_loss_distribution(results_dict, save_path=None)
  Bar chart: Wins vs Losses vs Neutral with win rate % shown.

FUNCTION: plot_signal_on_price(df, signal_dict, lookback=50, save_path=None)
  Plot last `lookback` candles as simple OHLC line chart.
  Mark: entry (green dashed), SL (red dashed), TP 2R (blue dashed), TP 4R (purple dashed).

Run me without errors. Import paths must work from both command line and Google Colab.
```

---

# PROMPT 3 — STRATEGY 2: FVA Ideal Setup Backtest

```
You are implementing Strategy 2 of 7 for the MMC Trading System.
This strategy was explicitly taught by Arjo in Videos 2, 3, 7 (FVA Types).

FOLDER: mmc_backtest/strategies/strategy_2_fva_ideal/
FILES TO CREATE: __init__.py, scanner.py, backtest.py, visualize.py

STRATEGY 2: FVA IDEAL SETUP — Complete Rules from Arjo

PURPOSE: Enter from a Triple Probability (IDEAL) Fair Value Area.

WHAT IS AN IDEAL FVA (from Arjo, video7_fva_types.py):
  An FVA is formed between two IT Points (Intermediate Term High + Low).
  IDEAL FVA requires ALL THREE:
    1. has_overlapping_fvg == True (a PFVG overlaps the FVA boundary)
    2. has_nested_fva == True (an inner smaller FVA exists inside)
    3. is_sweep == False (the FVA boundary has NOT been swept - still fresh)
  If ALL THREE: fva_type = 'IDEAL', probability_arrays = 3 (Triple Probability)

ARJO'S EXACT CONDITIONS (all must be TRUE):

CONDITION 1 - IDEAL FVA Must Be Present:
  - Scan for IT points using scan_it_points(df) from video2_market_structure.py
  - Build FVA from most recent IT_HIGH and IT_LOW pair
  - has_overlapping_fvg == True
  - has_nested_fva == True
  - is_sweep == False

CONDITION 2 - Price Is At Or Inside The FVA Boundary (NOT fully past it):
  - BULLISH FVA: price approaching from below or just entered fva_low
  - BEARISH FVA: price approaching from above or just entered fva_high

CONDITION 3 - OFL Is Present Inside Or At FVA Boundary:
  - OFL must be INSIDE the FVA zone (between fva_low and fva_high)
  - probability_label must be 'HIGH' or 'MEDIUM'

CONDITION 4 - No Opposing PDA Between FVA and Target:
  - Same as Strategy 1 Condition 4

ENTRY RULES:
  - Use NESTED FVA as the precision entry zone
  - BULLISH: entry_price = nested_fva_low
  - BEARISH: entry_price = nested_fva_high
  - If nested FVA not found: fall back to overlapping PFVG boundary

STOP LOSS:
  - BULLISH: fva_low - buffer (2 pips EURUSD/GBPUSD, 20 pips XAUUSD)
  - BEARISH: fva_high + buffer

TAKE PROFIT:
  - Primary: nearest IT_HIGH (bullish) or IT_LOW (bearish) outside the FVA
  - Also calculate tp_2r, tp_4r
  - Use the closer of: structural target or tp_4r
  - Minimum must be tp_2r, else SKIP

SCANNER: def scan_fva_ideal(df, instrument, timeframe) -> list[dict]

Signal dict:
{
  'strategy': 'FVA_IDEAL',
  'instrument', 'timeframe', 'signal_datetime',
  'direction': 'BULLISH' or 'BEARISH',
  'entry_price', 'stop_loss', 'tp_2r', 'tp_4r', 'risk_pips',
  'fva_high', 'fva_low',
  'nested_fva_high', 'nested_fva_low',
  'overlapping_fvg_high', 'overlapping_fvg_low', 'overlapping_fvg_type',
  'structural_target', 'structural_target_type',
  'probability_arrays': 3
}

BACKTEST: run_backtest(instrument, timeframe, data_dir=None) -> dict
  Same structure as Strategy 1.
  WIN = tp_2r hit. LOSS = SL hit. NEUTRAL = 100 candles pass.

VISUALIZE: Same 3 standard plots adapted for FVA labels.
Run without errors.
```

---

# PROMPT 4 — STRATEGY 3: FVA Good Setup Backtest

```
You are implementing Strategy 3 of 7 for the MMC Trading System.
This strategy was explicitly taught by Arjo in Videos 2, 3, 7.

FOLDER: mmc_backtest/strategies/strategy_3_fva_good/
FILES TO CREATE: __init__.py, scanner.py, backtest.py, visualize.py

STRATEGY 3: FVA GOOD SETUP — Complete Rules from Arjo

PURPOSE: Enter from a Double Probability (GOOD) Fair Value Area.

WHAT IS A GOOD FVA:
  GOOD FVA requires:
    1. has_overlapping_fvg == True (PFVG or BFVG overlaps FVA boundary)
    2. has_nested_fva == False (NO inner nested FVA - 2 probability arrays only)
    3. is_sweep == False
  fva_type = 'GOOD', probability_arrays = 2

Arjo says: "For a Good FVA, trade FROM the FVA boundary and FVG overlap zone."

ARJO'S EXACT CONDITIONS:

CONDITION 1 - GOOD FVA Must Be Present:
  - has_overlapping_fvg == True
  - has_nested_fva == False (if True this is Strategy 2)
  - is_sweep == False
  - overlapping_fvg_type must be 'PFVG' or 'BFVG' (NOT 'RFVG')

CONDITION 2 - Price Must Be At The Overlap Zone:
  - BULLISH: price at or just touching the FVG+FVA overlap_zone_low
  - BEARISH: price at or just touching the overlap_zone_high

CONDITION 3 - Candle Science Bias Aligns (from video5_candle_science.py):
  - Call get_candle_science_bias(instrument)
  - overall_bias must match the FVA direction
  - bias_confidence must be 'HIGH' or 'MEDIUM'

CONDITION 4 - No Opposing PDA Blocking: same as always.

ENTRY RULES:
  - BULLISH: entry_price = max(fvg_low, fva_low)  <- HIGHER of the two
  - BEARISH: entry_price = min(fvg_high, fva_high) <- LOWER of the two

STOP LOSS: OFL swing point +/- buffer (same rule)
TAKE PROFIT: minimum tp_2r, use structural target or tp_4r (closer)

SCANNER: def scan_fva_good(df, instrument, timeframe) -> list[dict]

Signal dict:
{
  'strategy': 'FVA_GOOD',
  'instrument', 'timeframe', 'signal_datetime', 'direction',
  'entry_price', 'stop_loss', 'tp_2r', 'tp_4r', 'risk_pips',
  'fva_high', 'fva_low',
  'probability_arrays': 2,
  'candle_science_bias': str,
  'overlap_zone_high': float, 'overlap_zone_low': float,
}

BACKTEST: run_backtest(instrument, timeframe, data_dir=None) -> dict
  Same structure. Include note in results that Good FVA (2 arrays) has lower expected win rate than Ideal (3 arrays).

VISUALIZE: Same 3 standard plots.
Run without errors.
```

---

# PROMPT 5 — STRATEGY 4: Sweep + OFL / MSS

```
You are implementing Strategy 4 of 7 for the MMC Trading System.
This strategy was explicitly taught by Arjo in Video 8 (Sweeps).

FOLDER: mmc_backtest/strategies/strategy_4_sweep_ofl/
FILES TO CREATE: __init__.py, scanner.py, backtest.py, visualize.py

STRATEGY 4: SWEEP + ORDER FLOW (MSS) — Complete Rules from Arjo

PURPOSE: Enter after a clean liquidity sweep of a swing point + OFL confirmation.

FROM ARJO (video8_sweeps.py logic):
  A SWEEP (not a RUN) happens when:
  - Price wicks BEYOND a swing point
  - Price CLOSES BACK inside (in the previous direction)
  - Less than 2 "comfortable" candles close beyond the swept level
  After a SWEEP: look for a CONTINUATION FVG in the sweep direction, then ENTER THERE

ARJO'S EXACT CONDITIONS:

CONDITION 1 - Clean Sweep Event:
  - classify_liquidity_event() result: event == 'SWEEP' (NOT 'RUN')
  - comfortable_candles <= 1 (immediate reversal - clean sweep)
  - Wick beyond swept level must be >= SWEEP_WICK_MIN_PIPS:
    EURUSD/GBPUSD: 2 pips, XAUUSD: 20 pips

CONDITION 2 - Continuation FVG Exists After Sweep:
  - After the sweep candle, a FVG must form in the SWEEP DIRECTION
  - BULLISH sweep (swept lows, going UP): continuation FVG must be BULLISH PFVG
  - BEARISH sweep (swept highs, going DOWN): continuation FVG must be BEARISH PFVG
  - fvg_type must be 'PFVG' (HIGH confidence) or 'BFVG' (MEDIUM). RFVG = reject.

CONDITION 3 - OFL Is Present At Or After Sweep:
  - OFL must exist in sweep direction with probability_label 'HIGH' or 'MEDIUM'

CONDITION 4 - is_aggressive == False:
  - If is_aggressive == True: "You missed it or it's a run" - SKIP TRADE

ENTRY:
  - BULLISH sweep: entry_price = continuation_fvg_low
  - BEARISH sweep: entry_price = continuation_fvg_high

STOP LOSS:
  - BULLISH: stop_loss = swept_swing_level - buffer (below wick low)
  - BEARISH: stop_loss = swept_swing_level + buffer (above wick high)

TAKE PROFIT:
  - Primary target: opposite swing point (BSL for bull, SSL for bear)
  - Minimum: tp_2r
  - If opposite swing < tp_2r distance: SKIP

SCANNER: def scan_sweep_ofl(df, instrument, timeframe) -> list[dict]

Signal dict:
{
  'strategy': 'SWEEP_OFL',
  'instrument', 'timeframe', 'signal_datetime', 'direction',
  'entry_price', 'stop_loss', 'tp_2r', 'tp_4r', 'risk_pips',
  'swept_level': float,
  'sweep_wick_pips': float,
  'continuation_fvg_high': float, 'continuation_fvg_low': float,
  'continuation_fvg_type': str,
  'ofl_probability': str,
  'comfortable_candles': int,
  'sweep_probability_score': float,
}

BACKTEST: run_backtest(instrument, timeframe, data_dir=None) -> dict
  WIN = tp_2r hit. LOSS = SL hit.
  EXTRA STATS: avg_sweep_wick_pips, pfvg_count vs bfvg_count, pct_immediate_reversals.

VISUALIZE:
  Standard 3 plots + 4th:
  plot_sweep_distribution(results_dict) -> bar chart of sweep wick pips distribution.

Run without errors.
```

---

# PROMPT 6 — STRATEGY 5: Candle Science Bias Entry

```
You are implementing Strategy 5 of 7 for the MMC Trading System.
This strategy was explicitly taught by Arjo in Video 5 (Candle Science).

FOLDER: mmc_backtest/strategies/strategy_5_candle_science/
FILES TO CREATE: __init__.py, scanner.py, backtest.py, visualize.py

STRATEGY 5: CANDLE SCIENCE BIAS ENTRY — Complete Rules from Arjo

PURPOSE: Use the HTF candle type to get directional bias, then enter on a lower TF in that direction.

ARJO'S CANDLE SCIENCE (from video5_candle_science.py):

DISRESPECT CANDLE (Bullish): UP candle, body_ratio >= 0.55, upper_wick_ratio < 0.30
DISRESPECT CANDLE (Bearish): DOWN candle, body_ratio >= 0.55, lower_wick_ratio < 0.30
RESPECT CANDLE (Bullish): lower_wick_ratio >= 0.30
RESPECT CANDLE (Bearish): upper_wick_ratio >= 0.30

TF PAIRS (from CANDLE_SCIENCE_TF_PAIRS in video5):
  MONTHLY -> DAILY, WEEKLY -> 4H, DAILY -> 1H, 4H -> 15M, 1H -> 5M

ARJO'S EXACT CONDITIONS:

CONDITION 1 - HTF Candle Science Signal:
  - Higher TF (DAILY or WEEKLY usually) shows DISRESPECT or RESPECT candle
  - candle_type must NOT be 'NEUTRAL'
  - confidence_score >= 60.0

CONDITION 2 - Lower TF OFL Aligns With HTF Bias:
  - Drop to entry TF per CANDLE_SCIENCE_TF_PAIRS
  - OFL direction must match HTF candle science direction
  - probability_label: 'HIGH' or 'MEDIUM'

CONDITION 3 - PFVG Exists on Entry TF OFL:
  - OFL must have fvg_type == 'PFVG' as the entry FVG

CONDITION 4 - 3-TF Bias Check:
  - get_candle_science_bias(instrument) -> overall_bias must match direction
  - bias_confidence: 'HIGH' or 'MEDIUM'

ENTRY: BULLISH = OFL's fvg_low. BEARISH = OFL's fvg_high.
STOP LOSS: OFL swing_point_price +/- buffer.
TAKE PROFIT: Structural target on entry TF. Minimum tp_2r.

SCANNER: def scan_candle_science(df_htf, df_ltf, instrument, htf, ltf) -> list[dict]
  (Needs TWO DataFrames - one per timeframe)

Signal dict:
{
  'strategy': 'CANDLE_SCIENCE',
  'instrument', 'signal_datetime',
  'htf', 'ltf', 'direction',
  'htf_candle_type': str,
  'htf_confidence': float,
  'ltf_ofl_probability': str,
  'entry_price', 'stop_loss', 'tp_2r', 'tp_4r', 'risk_pips',
  'bias_confidence': str,
}

BACKTEST: run_backtest(instrument, htf, ltf, data_dir=None) -> dict
  Load BOTH htf and ltf data.
  Align by date (only scan when both have data for same period).
  Same WIN/LOSS/NEUTRAL simulation.

VISUALIZE:
  Standard 3 plots + plot_htf_candle_types(results_dict):
  Pie chart of signal type breakdown (DISRESPECT_BULLISH/BEARISH, RESPECT_BULLISH/BEARISH).

Run without errors.
```

---

# PROMPT 7 — STRATEGY 6: Sharp Turn Entry

```
You are implementing Strategy 6 of 7 for the MMC Trading System.
This strategy was explicitly taught by Arjo in Video 11 (Entry Models).

FOLDER: mmc_backtest/strategies/strategy_6_sharp_turn/
FILES TO CREATE: __init__.py, scanner.py, backtest.py, visualize.py

STRATEGY 6: SHARP TURN ENTRY — Complete Rules from Arjo

PURPOSE: Enter when price enters a context area and forms a Sharp Turn pattern.
Sharp Turn = price enters zone + FVG_IN forms + FVG_OUT forms rapidly (1-3 candles).

FROM ARJO (video11_entries.py build_sharp_turn()):
  FVG_IN = FVG price enters into (the context area boundary FVG)
  FVG_OUT = FVG that forms AFTER price enters FVG_IN (actual entry FVG)
  "Sharp" = reversal is FAST, FVG_OUT forms within 1-3 candles of touching FVG_IN

Entry TF minimum rules (CONTEXT_TF_ENTRY_MAP in video11):
  Context DAILY -> Entry TF minimum: 1H (sharp_turn)
  Context 4H    -> Entry TF minimum: 15M
  Context 1H    -> Entry TF minimum: 5M

ARJO'S EXACT CONDITIONS:

CONDITION 1 - Active Context Area Exists:
  - build_context_area() from video10_context.py
  - context_area['is_active'] == True
  - context_area['is_target_reached'] == False

CONDITION 2 - Price Has Entered FVG_IN:
  - A PFVG (FVG_IN) must exist at context area boundary
  - Current candle must be inside FVG_IN range
  - BULLISH: current_low inside [fvg_in_low, fvg_in_high]
  - BEARISH: current_high inside [fvg_in_low, fvg_in_high]

CONDITION 3 - FVG_OUT Has Formed (within 1-3 candles of entering FVG_IN):
  - BULLISH: look for BULLISH PFVG or BFVG forming
  - BEARISH: look for BEARISH PFVG or BFVG forming

CONDITION 4 - OFL Exists In Entry TF:
  - probability_label at least 'MEDIUM'

CONDITION 5 - Entry TF Rule Validated:
  - validate_entry_timeframe(context_tf, entry_tf, 'sharp_turn') from video11
  - is_valid must be True (hard rule, do not bypass)

ENTRY (from build_sharp_turn() in video11):
  - BEARISH: entry_price = fvg_out['fvg_high']
  - BULLISH: entry_price = fvg_out['fvg_low']

STOP LOSS (Arjo's EXACT rule):
  - SL = most recent OFL's swing_point_price (ALWAYS at OFL swing, never arbitrary)

TAKE PROFIT:
  - PRIMARY: context_area['target_price']
  - Minimum distance must be >= tp_2r, else SKIP

SCANNER: def scan_sharp_turn(df_context_tf, df_entry_tf, instrument, context_tf, entry_tf) -> list[dict]

Signal dict:
{
  'strategy': 'SHARP_TURN',
  'instrument', 'context_tf', 'entry_tf', 'signal_datetime', 'direction',
  'entry_price', 'stop_loss', 'tp_2r', 'tp_4r', 'risk_pips',
  'fvg_in_high', 'fvg_in_low',
  'fvg_out_high', 'fvg_out_low', 'fvg_out_type',
  'context_target', 'context_target_type',
  'ofl_swing', 'candles_to_form_fvg_out': int,
}

BACKTEST: run_backtest(instrument, context_tf, entry_tf, data_dir=None) -> dict
  Align two TFs by date.
  WIN = context_target hit OR tp_2r hit. LOSS = SL hit.
  EXTRA STATS: avg_candles_to_form_fvg_out, % context_target hit vs tp_2r hit.

VISUALIZE: Standard 3 plots + plot_context_hit_vs_tp2r() (pie chart).

Run without errors.
```

---

# PROMPT 8 — STRATEGY 7: Order Flow Entry

```
You are implementing Strategy 7 of 7 for the MMC Trading System.
This strategy was explicitly taught by Arjo in Video 11 (Entry Models).

FOLDER: mmc_backtest/strategies/strategy_7_order_flow_entry/
FILES TO CREATE: __init__.py, scanner.py, backtest.py, visualize.py

STRATEGY 7: ORDER FLOW ENTRY — Complete Rules from Arjo

PURPOSE: Enter using TWO sequential OFLs in same direction inside an active context area.
Arjo's rule: "For Order Flow entry, you need OFL ONE + OFL TWO. OFL two is your entry."

WHAT ARE TWO OFLs?
  OFL 1 = First OFL identified (older, higher TF confirmation)
  OFL 2 = Second MORE RECENT OFL in SAME direction (newer, lower TF - actual entry)
  Both in same direction = price is COMMITTED to move that way.

ARJO'S EXACT CONDITIONS:

CONDITION 1 - Active Context Area Exists:
  - Same as Strategy 6 Condition 1

CONDITION 2 - TWO OFLs In Same Direction On Entry TF:
  - scan_candles_for_ofls(df_entry_tf, instrument)
  - Filter: same direction as trade
  - Sort by datetime descending: ofl_1 = ofls[0], ofl_2 = ofls[1]
  - BOTH: same direction
  - BOTH: probability_label 'HIGH' or 'MEDIUM'
  - BOTH: is_confirmed == True

CONDITION 3 - OFL 2 Is Inside Active Context:
  - OFL 2's FVG must be WITHIN context area boundaries

CONDITION 4 - Entry TF Rule Validated:
  - validate_entry_timeframe(context_tf, entry_tf, 'order_flow') from video11
  Entry TF minimums (from CONTEXT_TF_ENTRY_MAP):
    Context MONTHLY -> Entry min 4H
    Context WEEKLY  -> Entry min 1H
    Context DAILY   -> Entry min 15M
    Context 4H      -> Entry min 5M
    Context 1H      -> Entry min 1M

CONDITION 5 - MMC 10-Point Checklist (run_mmc_checklist from video11):
  1. DIRECTION - OFL aligns with context
  2. NARRATIVE - Context area active
  3. FVG QUALITY - PFVG ideally
  4. FVA QUALITY - IDEAL or GOOD FVA
  5. H-TF TIME - Higher TF news supports (WARN in backtest)
  6. L-TF TIME - In killzone: 02:00-10:00 NY (WARN in backtest)
  7. CONTEXT - Target not reached
  8. ENTRY TF - TF rule passes
  9. CONFIRMATION - OFL 2 formed
  10. BIG THREE - No major news within 30 mins (WARN in backtest)
  Items 5,6,10 = WARN (not hard fail in backtest). Items 1,2,3,7,8,9 = must PASS.

ENTRY (from build_order_flow_entry() in video11):
  - BEARISH: entry_price = ofl_2['fvg_high']
  - BULLISH: entry_price = ofl_2['fvg_low']

STOP LOSS (Arjo's rule):
  - SL = ofl_2['swing_point_price'] (ALWAYS OFL 2 swing, never arbitrary)

TAKE PROFIT:
  - PRIMARY: context_area['target_price']
  - Also: tp_2r, tp_4r (take closer)
  - Minimum: tp_2r else SKIP

SCANNER: def scan_order_flow_entry(df_context_tf, df_entry_tf, instrument, context_tf, entry_tf) -> list[dict]

Signal dict:
{
  'strategy': 'ORDER_FLOW_ENTRY',
  'instrument', 'context_tf', 'entry_tf', 'signal_datetime', 'direction',
  'entry_price', 'stop_loss', 'tp_2r', 'tp_4r', 'risk_pips',
  'ofl_1_swing', 'ofl_1_probability',
  'ofl_2_swing', 'ofl_2_probability', 'ofl_2_fvg_type',
  'context_target', 'context_target_type',
  'checklist_passed': bool,
  'checklist_failed_items': list[str],
}

BACKTEST: run_backtest(instrument, context_tf, entry_tf, data_dir=None) -> dict
  WIN = context_target OR tp_2r hit. LOSS = SL hit.
  EXTRA STATS: % signals fully checklist-passed, OFL probability distributions.

VISUALIZE: Standard 3 plots + plot_checklist_failures(results_dict):
  Horizontal bar chart showing which checklist item fails most often.

Run without errors.
```

---

# PROMPT 9 — MASTER CONTEXT PROMPT (Use this to start a NEW fresh chat)

```
MMC TRADING SYSTEM - COMPLETE PROJECT CONTEXT FOR NEW CHAT
Built from Arjo's 12-Video MMC Trading Course

PROJECT LOCATION: c:\Users\Admin\OneDrive\Desktop\MMC\mmc_backtest\

=== SECTION 1: WHO IS ARJO AND WHAT IS MMC? ===

Arjo is a professional Forex/Gold trader who teaches the "MMC" (Money Market Concepts)
trading methodology. The course has exactly 12 videos. Each video has been transcribed and
translated into Python code files (video1_pd_arrays.py through video12_top_down.py) which
serve as the GROUND TRUTH for this project. All strategy implementation must follow ONLY what
Arjo explicitly taught in these videos.

=== SECTION 2: THE 7 STRATEGIES ARJO SHARED (EXACT) ===

1. OFL CONTINUATION - Enter at PFVG of High-Probability OFL. PFVG + HIGH OFL + direction match + clear path. SL at OFL swing +/- 2 pips. TP minimum 2R.

2. FVA IDEAL SETUP - Enter from IDEAL FVA (overlapping PFVG + nested FVA + not swept). Enter at nested FVA boundary. SL at FVA boundary +/- buffer. TP = IT_HIGH/IT_LOW, minimum 2R.

3. FVA GOOD SETUP - Enter from GOOD FVA (overlapping FVG, no nested FVA, not swept). Enter at FVG+FVA overlap. Needs candle science confirmation. SL at OFL swing. TP minimum 2R.

4. SWEEP + OFL (MSS) - Enter after clean liquidity sweep + continuation PFVG + OFL. SL at sweep wick extreme +/- buffer. TP = opposite swing target, minimum 2R.

5. CANDLE SCIENCE BIAS - Identify DISRESPECT or RESPECT candle on HTF (D1/W1). Drop to lower TF, find OFL with PFVG in same direction. Enter at PFVG. SL at OFL swing. TP minimum 2R.

6. SHARP TURN ENTRY - Price enters context area, FVG_IN forms, then FVG_OUT forms (1-3 candles). Enter at FVG_OUT. SL at most recent OFL swing. TP = context target. Minimum TF rule applies.

7. ORDER FLOW ENTRY - Two OFLs in same direction on entry TF inside active context area. Enter at OFL 2 FVG. SL at OFL 2 swing. TP = context target. 10-point MMC checklist required.

=== SECTION 3: KEY CONCEPTS FROM THE VIDEOS ===

PD ARRAYS (Video 1): FVG > FVA > SWING_POINT (hierarchy)
  FVG Types: PFVG (rejection_ratio < 0.25) = TRADE IT | BFVG (breakaway) = DROP TF | RFVG (rejection) = AVOID
  Bullish FVG: gap between candle1_high and candle3_low (c3_low > c1_high required)
  Bearish FVG: gap between candle1_low and candle3_high (c3_high < c1_low required)
  Pip multipliers: EURUSD/GBPUSD = 10000, XAUUSD = 10

MARKET STRUCTURE (Video 2): IT Points = highest/lowest of 3 consecutive swing highs/lows.
  Higher IT High + Higher IT Low = BULLISH trend. FVA = zone between IT_HIGH and IT_LOW.
  Market states: OFFERING_FAIR_VALUE (inside FVA), SEEKING_LIQUIDITY (below/above FVA), BEYOND_FVA.

ORDER FLOW (Videos 3-4): OFL = Swing Point + FVG after it.
  Components: LOD (swing) + FLOD (first PDA = FVG or FVA, whichever hit first) + ODD (overlap zone).
  Scoring: FLOD(40) + ODD(35) + FVG_type_score + FVA_type_score + LOD_score. Max=130.
  HIGH OFL = normalized score >= 75%. RFVG = AUTO LOW regardless of score.
  OFL invalidated if price closes BELOW swing low (bull) or ABOVE swing high (bear).

CANDLE SCIENCE (Video 5): Body ratio >= 55% + specific wick = DISRESPECT or RESPECT.
  Confidence = body_score(30pts) + wick_score(30pts) + ofl_alignment_score(40pts).
  3-TF bias check: Monthly + Weekly + Daily. All 3 same = HIGH bias. 2 same = MEDIUM.

FVG TYPES (Video 6): PFVG = ideal. BFVG = drop TF. RFVG = avoid.
  Opposing PDA confluence = +15pts probability. Sweep after FVG = -20pts. RFVG capped at 40pts.

FVA TYPES (Video 7): IDEAL (all 3 criteria) > GOOD (2) > WEAK (swept or only 1).
  probability_arrays = 3/2/1. Nested FVA = precision zone. Sweep of FVA = -25pts penalty.
  Base scores: IDEAL=90, GOOD=70, WEAK=20.

SWEEPS (Video 8): SWEEP = wick beyond swing + close back. comfortable_candles <= 1.
  MinWick: EURUSD/GBPUSD 2pips, XAUUSD 20pips. is_aggressive = after-candle body > 70% range.
  SWEEP base probability = 70. Aggressive penalty = -30. Continuation FVG = +15. Immediate reversal = +10.

TIME (Video 9): Killzone = 02:00 to 10:00 NY time (forex instruments).
  Big Three = NFP (Friday), FOMC Statement, CPI. Do NOT trade day BEFORE Big Three.
  Big Three day = trade after release (wait 5 minutes minimum). No news = no trade day.

CONTEXT AREAS (Video 10): From PDA boundary to first opposing PDA = context zone.
  Defense types: FVG boundary = FLOD | FVA boundary = ODD | Swing point = LOD.
  Unusual context = FVA disrespected, market shifts to liquidity seeking mode.

ENTRIES (Video 11):
  SHARP TURN: FVG_IN entered -> FVG_OUT forms (1-3 candles). SL = most recent OFL swing.
  ORDER FLOW: OFL1 + OFL2 same direction. Enter at OFL2 FVG. SL = OFL2 swing.
  Context-to-Entry TF minimums:
    Context MONTHLY: SharpTurn min=DAILY, OrderFlow min=4H
    Context WEEKLY:  SharpTurn min=4H,    OrderFlow min=1H
    Context DAILY:   SharpTurn min=1H,    OrderFlow min=15M
    Context 4H:      SharpTurn min=15M,   OrderFlow min=5M
    Context 1H:      SharpTurn min=5M,    OrderFlow min=1M
  10-Point Checklist: Direction, Narrative, FVG Quality, FVA Quality, H-TF Time, L-TF Time, Context, Entry TF, Confirmation, Big Three.

TOP DOWN (Video 12): Weekly OFL + Daily OFL + 4H/1H contexts. Most arguments = trade direction.
  Trade readiness: NOT_READY -> LOW -> MEDIUM -> (HIGH with news check).

=== SECTION 4: FOLDER STRUCTURE (AFTER CLEANUP) ===

mmc_backtest/
  modules/                        <- VIDEO TRANSLATIONS (DO NOT MODIFY)
    video1_pd_arrays.py           <- PD Arrays, FVG detection, swing points
    video2_market_structure.py    <- IT points, FVA boundaries, trend
    video3_4_order_flow.py        <- OFL building, FLOD/ODD/LOD, scoring
    video5_candle_science.py      <- Candle metrics, DISRESPECT/RESPECT
    video6_fvg_types.py           <- PFVG/BFVG/RFVG full analysis
    video7_fva_types.py           <- IDEAL/GOOD/WEAK FVA full analysis
    video8_sweeps.py              <- Sweep detection, RUN vs SWEEP
    video9_time.py                <- Killzones, Big Three, weekly profile
    video10_context.py            <- Context areas, defense zones
    video11_entries.py            <- Sharp Turn, Order Flow, MMC checklist, RR
    video12_top_down.py           <- Top-down bias, session stats
  backtest/
    data_loader.py                <- MT5 CSV loader
    results/                      <- JSON outputs per strategy per instrument
  strategies/
    strategy_1_ofl_continuation/  scanner.py, backtest.py, visualize.py
    strategy_2_fva_ideal/         scanner.py, backtest.py, visualize.py
    strategy_3_fva_good/          scanner.py, backtest.py, visualize.py
    strategy_4_sweep_ofl/         scanner.py, backtest.py, visualize.py
    strategy_5_candle_science/    scanner.py, backtest.py, visualize.py
    strategy_6_sharp_turn/        scanner.py, backtest.py, visualize.py
    strategy_7_order_flow_entry/  scanner.py, backtest.py, visualize.py
  data/
    raw/                          <- YOUR MT5 CSV FILES
      EURUSD_D1.csv, EURUSD_H4.csv, EURUSD_H1.csv, EURUSD_M15.csv, EURUSD_M5.csv
      GBPUSD_D1.csv ... etc
      XAUUSD_D1.csv ... etc
  colab/
    arjo_mmc_backtest.ipynb       <- MASTER COLAB NOTEBOOK

=== SECTION 5: DATA FORMAT (MT5 EXPORT) ===

CSV header: <DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<TICKVOL>,<VOL>,<SPREAD>
Example row: 2024.01.02,02:00,1.09500,1.09600,1.09400,1.09550,1000,0,2
Date format: YYYY.MM.DD  |  Time format: HH:MM
After parsing: datetime = "YYYY-MM-DD HH:MM:SS". Drop weekends.

=== SECTION 6: ARJO'S RULES (NEVER VIOLATE) ===

1. RFVG = NEVER enter directly. Avoid or drop TF.
2. SL is ALWAYS at the OFL SWING POINT. Never arbitrary.
3. Minimum TP = 2R. Never take less.
4. No unmitigated opposing PDA between entry and TP: SKIP.
5. Do NOT trade day before Big Three event.
6. Wait 5 minutes AFTER Big Three release before entering.
7. NEVER analyze forming candle. Always use iloc[-2] (last closed candle).
8. Killzone for forex = 02:00 to 10:00 NY time ONLY.
9. Two OFLs must be same direction for Order Flow entry.
10. SWEEP = close BACK within swept level. If not: it is a RUN, not a sweep.

=== SECTION 7: WHAT NOT TO DO ===

DO NOT invent strategies not in the 12 videos.
DO NOT use ICT-style entries (not Arjo's method).
DO NOT use 25 strategies (the old AI-generated list was WRONG).
DO NOT trade RFVG directly.
DO NOT violate minimum TF entry rules.
DO NOT modify the video1-12 .py files (they are ground truth).
DO NOT add Flask, APIs, or dashboards. This is pure Python backtesting.

Now proceed with: [STATE YOUR SPECIFIC TASK FOR THIS CHAT HERE]
```

---

*END OF MASTER PROMPTS*
*See arjo_mmc_backtest.ipynb for the Colab notebook (generated separately)*

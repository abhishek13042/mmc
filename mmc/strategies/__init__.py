"""Seven MMC trading strategies — with ITH/ITL as the liquidity target.

The target of every trade is the next **Intermediate-Term High** (for bullish
trades) or **Intermediate-Term Low** (for bearish trades): the real liquidity
level the market is moving toward (transcripts 01, 03, 04 — swing points are
sell-side / buy-side liquidity; the market always targets them).

Each strategy function accepts ``ctx_tf`` (context timeframe) and ``entry_tf``
(entry confirmation timeframe), so the full Arjo top-down cascade is supported:
  D1 context → H4 entries
  H4 context → H1 entries
  H1 context → M15 entries
  M15 context → M5 entries

All seven strategies share the same liquidity-target patching so the TP is
always at the nearest ITH/ITL price, giving a variable but real-world RR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from mmc.backtest.engine import run_backtest
from mmc.backtest.result import BacktestResult
from mmc.context import ContextArea, find_context_areas, find_unusual_context
from mmc.core import Direction, Zone
from mmc.core import find_fvgs, find_swings, mark_mitigation
from mmc.core.structure import intermediate_term_points
from mmc.core.types import Timeframe
from mmc.data import load
from mmc.entry import Entry, find_entries
from mmc.entry.signal import make_take_profit
from mmc.sweeps.liquidity import liquidity_sweeps
from mmc.topdown import TraderStyle, best_pair

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD"]
DEFAULT_BARS = 1_000

# Timeframe combos: (context_tf, entry_tf, label)
TF_COMBOS: List[Tuple[Timeframe, Timeframe, str]] = [
    (Timeframe.D1,  Timeframe.H4,  "D1→H4"),
    (Timeframe.H4,  Timeframe.H1,  "H4→H1"),
    (Timeframe.H1,  Timeframe.M15, "H1→M15"),
    (Timeframe.M15, Timeframe.M5,  "M15→M5"),
]


# ---------------------------------------------------------------------------
# Liquidity-target helpers
# ---------------------------------------------------------------------------

def _ith_itl_from(symbol: str, ctx_tf: Timeframe, bars: int) -> list:
    """Return ITH/ITL structure points from the context-TF data."""
    ctx_df = load(symbol, ctx_tf).iloc[-bars:]
    swings = find_swings(ctx_df)
    return intermediate_term_points(swings)


def _nearest_liquidity_target(
    direction: Direction,
    entry_price: float,
    it_points: list,
) -> Optional[float]:
    """Price of the nearest ITH (bullish) or ITL (bearish) beyond the entry.

    Uses PRICE distance rather than bar index so it works across timeframes:
    the context-TF ITH/ITL is valid as a price target on the entry TF.

    Returns None when no suitable level exists in the available data.
    """
    if direction is Direction.BULLISH:
        # ITH = premium above us = sell-side liquidity = our target
        candidates = [p for p in it_points if p.is_high and p.price > entry_price]
    else:
        # ITL = discount below us = buy-side liquidity = our target
        candidates = [p for p in it_points if not p.is_high and p.price < entry_price]
    if not candidates:
        return None
    # Nearest ITH/ITL in the correct direction
    return min(candidates, key=lambda p: abs(p.price - entry_price)).price


def _apply_liquidity_targets(
    entries: List[Entry],
    it_points: list,
    min_rr: float = 2.0,
) -> List[Entry]:
    """Patch every entry's take_profit to the nearest ITH/ITL price.

    Filters out entries where:
    - No ITH/ITL exists in the correct direction.
    - The ITH/ITL gives less than ``min_rr`` (target too close to entry — not
      worth the trade; transcript 11 ~16:18 targets at least 1:2 but we allow
      min_rr=1.0 here to keep the dataset meaningful).
    - The ITH/ITL is on the wrong side of the entry (degenerate data).
    """
    out: List[Entry] = []
    for e in entries:
        liq = _nearest_liquidity_target(e.direction, e.entry_price, it_points)
        if liq is None:
            continue
        risk = abs(e.entry_price - e.stop_loss)
        if risk <= 0:
            continue
        rr = abs(liq - e.entry_price) / risk
        if rr < min_rr:
            continue  # target too close
        # Direction sanity: bullish TP must be above entry, bearish below
        if e.direction is Direction.BULLISH and liq <= e.entry_price:
            continue
        if e.direction is Direction.BEARISH and liq >= e.entry_price:
            continue
        e.take_profit = liq
        e.rr = rr
        out.append(e)
    return out


def _load_pair(symbol: str, ctx_tf: Timeframe, entry_tf: Timeframe, bars: int):
    """Return (ctx_df, entry_df) sliced to the most recent ``bars``."""
    # Scale ctx bars so ctx_df covers roughly the same wall-clock period
    ratio = max(1, ctx_tf.minutes // entry_tf.minutes)
    ctx_bars = max(bars // ratio, 200)
    ctx_df = load(symbol, ctx_tf).iloc[-ctx_bars:]
    entry_df = load(symbol, entry_tf).iloc[-bars:]
    return ctx_df, entry_df


def _run(
    symbol: str,
    ctx_tf: Timeframe,
    entry_tf: Timeframe,
    bars: int,
    defense_filter: Optional[str] = None,  # "FLOD" | "ODD" | "LOD" | None = all
    unusual: bool = False,               # use find_unusual_context instead
    entry_type: str = "sharp_turn",
    bias_filter: Optional[Direction] = None,
) -> BacktestResult:
    """Core runner shared by all strategies.

    Builds context areas on ``ctx_tf``, finds entries on ``entry_tf``,
    patches every TP to the nearest ITH/ITL from the context TF, then
    runs the fill simulator.
    """
    ctx_df, entry_df = _load_pair(symbol, ctx_tf, entry_tf, bars)
    it_points = intermediate_term_points(find_swings(ctx_df))

    if unusual:
        areas = find_unusual_context(ctx_df)
    else:
        areas = find_context_areas(ctx_df)

    if defense_filter:
        areas = [a for a in areas if a.defense == defense_filter]
    if bias_filter:
        areas = [a for a in areas if a.direction is bias_filter]

    entries: List[Entry] = []
    for ctx in areas:
        entries.extend(find_entries(ctx, entry_df, entry_type=entry_type))

    entries = _apply_liquidity_targets(entries, it_points)
    entries.sort(key=lambda e: e.index)
    return run_backtest(entries, entry_df)


# ---------------------------------------------------------------------------
# S1 — Filtering Process (transcript 12)
# ---------------------------------------------------------------------------

def s1_filtering_process(
    symbols: List[str] = SYMBOLS,
    bars: int = DEFAULT_BARS,
    ctx_tf: Timeframe = Timeframe.H4,
    entry_tf: Timeframe = Timeframe.H1,
) -> BacktestResult:
    """Multi-pair filtering process: pick the highest-probability pair via the
    top-down bias engine, filter direction, then backtest it.

    The bias direction from the filtering process is used to filter context
    areas — only trades aligned with the bias are taken. TP = nearest ITH/ITL.
    """
    picked = best_pair(symbols, style=TraderStyle.FILTERING_PROCESS, bars=500)
    symbol = picked.symbol if picked else symbols[0]
    bias_dir = picked.direction if picked else None

    return _run(
        symbol, ctx_tf, entry_tf, bars,
        defense_filter=None,
        bias_filter=bias_dir,
    )


# ---------------------------------------------------------------------------
# S2 — Flow Trader (transcript 12)
# ---------------------------------------------------------------------------

def s2_flow_trader(
    symbol: str = "EURUSD",
    bars: int = DEFAULT_BARS,
    ctx_tf: Timeframe = Timeframe.H1,
    entry_tf: Timeframe = Timeframe.M15,
) -> BacktestResult:
    """Single-instrument flow trader: H1 context → M15 entry (default).

    Runs both sharp_turn and order_flow entries, deduplicates, patches TP
    to the nearest ITH/ITL from the context TF. Targets the next liquidity
    level so the RR varies per trade (as it does in live trading).
    """
    ctx_df, entry_df = _load_pair(symbol, ctx_tf, entry_tf, bars)
    it_points = intermediate_term_points(find_swings(ctx_df))
    areas = find_context_areas(ctx_df)

    entries: List[Entry] = []
    for ctx in areas:
        entries.extend(find_entries(ctx, entry_df, entry_type="sharp_turn"))
        entries.extend(find_entries(ctx, entry_df, entry_type="order_flow"))

    # Deduplicate same bar + direction
    entries.sort(key=lambda e: e.index)
    seen: set = set()
    unique: List[Entry] = []
    for e in entries:
        k = (e.index, e.direction)
        if k not in seen:
            seen.add(k)
            unique.append(e)

    unique = _apply_liquidity_targets(unique, it_points)
    unique.sort(key=lambda e: e.index)
    return run_backtest(unique, entry_df)


# ---------------------------------------------------------------------------
# S3 — FLOD Trade (transcripts 04 + 10)
# ---------------------------------------------------------------------------

def s3_flod(
    symbol: str = "EURUSD",
    bars: int = DEFAULT_BARS,
    ctx_tf: Timeframe = Timeframe.H1,
    entry_tf: Timeframe = Timeframe.M15,
) -> BacktestResult:
    """FLOD-only: FVG is the first line of defense — highest probability lag.

    TP = nearest ITH (bullish) or ITL (bearish) from the context TF,
    confirming that the full move to liquidity is the intended target.
    """
    return _run(symbol, ctx_tf, entry_tf, bars, defense_filter="FLOD")


# ---------------------------------------------------------------------------
# S4 — ODD Trade (transcripts 04 + 10)
# ---------------------------------------------------------------------------

def s4_odd(
    symbol: str = "EURUSD",
    bars: int = DEFAULT_BARS,
    ctx_tf: Timeframe = Timeframe.H1,
    entry_tf: Timeframe = Timeframe.M15,
) -> BacktestResult:
    """ODD-only: FVA + FVG overlap zone — double probability.

    TP = nearest ITH/ITL. The overlap zone is the best retrace point;
    the market is expected to deliver all the way to the liquidity level.
    """
    return _run(symbol, ctx_tf, entry_tf, bars, defense_filter="ODD")


# ---------------------------------------------------------------------------
# S5 — Unusual Context / LOD Liquidity Hunt (transcripts 04 + 10)
# ---------------------------------------------------------------------------

def s5_unusual_context(
    symbol: str = "EURUSD",
    bars: int = DEFAULT_BARS,
    ctx_tf: Timeframe = Timeframe.H1,
    entry_tf: Timeframe = Timeframe.M15,
) -> BacktestResult:
    """Unusual context: FVA rejection fails → opposing FVG → LOD is hunted.

    TP is set to the LOD swing point (ITH or ITL) — the exact liquidity level
    the market is now seeking. This is the highest-conviction target in MMC:
    once a FVA stops offering fair value, the LOD WILL be reached.
    """
    return _run(symbol, ctx_tf, entry_tf, bars, unusual=True)


# ---------------------------------------------------------------------------
# S6 — Turtle Soup / Liquidity Sweep (transcript 08)
# ---------------------------------------------------------------------------

def s6_turtle_soup(
    symbol: str = "EURUSD",
    bars: int = DEFAULT_BARS,
    ctx_tf: Timeframe = Timeframe.H1,
    entry_tf: Timeframe = Timeframe.M15,
    sweep_window: int = 3,
    rr: float = 2.0,
) -> BacktestResult:
    """Turtle soup: ITH/ITL swept → aggressive reversal FVG → entry.

    After a liquidity sweep the reversal FVG is the entry. SL is at the
    swept swing level. TP is patched to the nearest ITH/ITL in the reversal
    direction — price swept the first level to fuel a move to the NEXT one.
    """
    ctx_df, entry_df = _load_pair(symbol, ctx_tf, entry_tf, bars)
    it_points = intermediate_term_points(find_swings(ctx_df))

    # Turtle soup detection runs on entry TF (higher resolution sweeps)
    swings = find_swings(entry_df)
    fvgs = find_fvgs(entry_df)
    mark_mitigation(entry_df, fvgs)
    sweeps = liquidity_sweeps(entry_df, swings, window=sweep_window, fvgs=fvgs)

    entries: List[Entry] = []
    seen: set = set()
    for sweep in sweeps:
        rev_fvg = sweep.signal_fvg
        rev_dir = sweep.reversal_direction
        if rev_fvg is None or rev_dir is None:
            continue
        if rev_fvg.c3_index in seen:
            continue
        seen.add(rev_fvg.c3_index)

        sl = sweep.swing.price
        ep = rev_fvg.top if rev_dir is Direction.BEARISH else rev_fvg.bottom
        risk = abs(ep - sl)
        if risk <= 0:
            continue
        tp = make_take_profit(ep, sl, rr=rr)

        target_z = Zone(
            top=max(tp, ep) + 1e-5,
            bottom=min(tp, ep) - 1e-5,
            index=rev_fvg.c3_index,
            direction=rev_dir,
        )
        ctx = ContextArea(
            boundary=rev_fvg, target=target_z,
            direction=rev_dir, kind="usual", defense="LOD",
        )
        entries.append(Entry(
            direction=rev_dir, entry_zone=rev_fvg,
            stop_loss=sl, take_profit=tp,
            context=ctx, entry_type="turtle_soup",
            index=rev_fvg.c3_index, rr=rr,
        ))

    # Patch TP to next ITH/ITL (the real liquidity beyond the swept level)
    entries = _apply_liquidity_targets(entries, it_points)
    entries.sort(key=lambda e: e.index)
    return run_backtest(entries, entry_df)


# ---------------------------------------------------------------------------
# S7 — LOD Swing Sweep / No-FVG Lag (transcripts 04 + 10)
# ---------------------------------------------------------------------------

def s7_lod_swing_sweep(
    symbol: str = "EURUSD",
    bars: int = DEFAULT_BARS,
    ctx_tf: Timeframe = Timeframe.H1,
    entry_tf: Timeframe = Timeframe.M15,
) -> BacktestResult:
    """LOD swing sweep: no FVG in the lag — the swing IS the only defense.

    The sweep of the swing point is the entry trigger. TP = nearest ITH/ITL:
    if the swing is the only PD array in the lag, the market must reach the
    next liquidity level before any other defense can hold it back.
    """
    return _run(symbol, ctx_tf, entry_tf, bars, defense_filter="LOD")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "s1_filtering_process", "s2_flow_trader",
    "s3_flod", "s4_odd", "s5_unusual_context",
    "s6_turtle_soup", "s7_lod_swing_sweep",
    "SYMBOLS", "DEFAULT_BARS", "TF_COMBOS",
]

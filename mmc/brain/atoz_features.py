"""ATOZ concept features for the MMC decision brain v2.

Brain v1 (``features.py``) extracts 31 features from the **mmc** engine. This
module adds a parallel block of features sourced from the **atoz** library — the
faithful, transcript-by-transcript implementation of the ICT A-Z Guide
(episodes 1-39, see ``atoz/README.md``). v2 concatenates the two so the network
can learn weights over BOTH knowledge bases and tell us which library's concepts
carry the real edge.

Design — precompute once, look up per bar
-----------------------------------------
The atoz detectors run over a whole DataFrame. Re-running them inside every
candidate's look-back window would be slow, so :class:`AtozSignals` runs each
detector ONCE over the full entry timeframe (and the HTF), stores per-bar
lookups, and :func:`AtozSignals.extract` then does cheap dictionary/array reads.

Every detector is wrapped defensively: a failure degrades that feature to 0.0
rather than killing the dataset build (same contract as v1).

Leak safety
-----------
- HTF (mmxm) daily bias for an entry bar uses the most recent HTF bias whose
  timestamp is strictly BEFORE the entry bar's calendar day — never the bias of
  the still-forming HTF candle.
- All entry-tf signals are keyed on the bar at which the pattern *resolves*
  (``resolve_index`` / ``.index`` / ``end_index``), so a feature is only "on"
  once the pattern is actually visible.

The ATOZ time windows are in BROKER time (EET); because EET and NY both observe
DST, NY-referenced windows are constant in broker time (see ``atoz.timing``).
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from mmc.core import Direction as MmcDirection

# ATOZ imports — the second knowledge base
from atoz.core.types import Direction as AzDirection
from atoz.core.swings import find_swings as az_find_swings
from atoz.core.fvg import find_fvgs as az_find_fvgs


# ---------------------------------------------------------------------------
# Feature names (all NEW relative to the 31 mmc features)
# ---------------------------------------------------------------------------

ATOZ_FEATURE_NAMES: List[str] = [
    # Timing / killzone plans — ep 29-30, 33
    "az_silver_bullet",      # bar inside a Silver-Bullet window (ep 33)
    "az_london_setup",       # a London killzone plan setup resolves here (ep 29)
    "az_ny_setup",           # a New York killzone plan setup resolves here (ep 30)
    "az_session_reversal",   # the session setup is a REVERSAL variation (ep 29-30)
    # FVG secret story — ep 24
    "az_sweep",              # FVG-in-leg ABSENT → external liquidity sweep
    "az_run",                # FVG-in-leg PRESENT → internal rebalancing run
    "az_targets_opposing",   # the sweep/run draws toward opposing liquidity
    # ST (sharp-turn) model — ep 22-23 ("MSS is BS")
    "az_st_present",         # an ST entry resolves at this bar
    "az_st_dir_match",       # the ST direction agrees with the candidate
    # Dealing range / DOL — ep 20-21
    "az_in_premium",         # price in the premium half of the live dealing range
    "az_in_discount",        # price in the discount half
    "az_in_ote",             # price in the 0.62-0.79 OTE retracement band
    "az_dol_distance",       # signed, range-normalised distance to the -1.0 DOL
    # Market-Maker model / daily bias — ep 34, 36
    "az_mmxm_bias",          # HTF FVG daily bias (+1 bull / -1 bear / 0 neutral)
    "az_mmxm_bias_match",    # bias agrees with the candidate direction
    "az_lag_strong",         # the live entry-tf lag carries an FVG (strong, ep 36)
    # Turtle soup — ep 28
    "az_seek_destroy",       # a seek-and-destroy reversal resolves here
    "az_strength_weakness",  # a buying-on-strength / selling-on-weakness signal
    "az_double_quadrant",    # price sits in a premium-premium / discount-discount
    # Market-structure secrets — ep 32
    "az_intermediate",       # bar is an intermediate-term high/low (ITH/ITL)
    "az_tier_protected",     # the live swing tier is protected / has a leg FVG
    # Consolidation — ep 27
    "az_consolidating",      # price is inside a detected consolidation
    # Power of 3 / Judas — ep 18-19
    "az_manipulation",       # bar is in the manipulation (Judas) phase of a session
    # LP vs HP meta — ep 26 (100/0 one-sided = HP, ANY opposition = LP)
    "az_hp_condition",       # all live atoz directional arguments point one way
]

N_ATOZ_FEATURES = len(ATOZ_FEATURE_NAMES)

# Silver-Bullet windows in BROKER time (ep 33: NY 03-04, 10-11, 14-15 → +7).
_SB_WINDOWS_BROKER: List[Tuple[int, int]] = [(10, 11), (17, 18), (21, 22)]


def _to_mmc_dir(az_dir) -> Optional[MmcDirection]:
    """Map an atoz Direction onto an mmc Direction (by value)."""
    if az_dir is None:
        return None
    try:
        return MmcDirection.BULLISH if az_dir.value == "bullish" else MmcDirection.BEARISH
    except Exception:
        return None


@dataclass
class AtozSignals:
    """Precomputed atoz detector outputs for one symbol, with per-bar lookups."""

    entry_df: pd.DataFrame

    # per-bar lookups (keyed on the entry-tf bar where the pattern resolves)
    st_dir: Dict[int, str] = field(default_factory=dict)            # idx -> 'bullish'/'bearish'
    sweep_run: Dict[int, Tuple[str, bool]] = field(default_factory=dict)  # idx -> (story, targets_opposing)
    seek_destroy: Dict[int, str] = field(default_factory=dict)      # idx -> direction
    strength_weak: Dict[int, str] = field(default_factory=dict)     # idx -> direction
    session_setup: Dict[int, Tuple[str, str]] = field(default_factory=dict)  # idx -> (session, variation, dir) packed
    tier_at: Dict[int, Tuple[str, bool, bool]] = field(default_factory=dict)  # swing idx -> (tier, has_leg_fvg, protected)
    intermediate_bars: set = field(default_factory=set)            # swing idxs that are ITH/ITL
    quadrant_at: Dict[int, str] = field(default_factory=dict)       # idx -> quadrant name

    consolidation_mask: Optional[np.ndarray] = None                # bool per entry bar
    dealing_ranges: List = field(default_factory=list)             # sorted by .index

    # HTF mmxm bias, leak-safe: list of (timestamp, signed_bias) sorted by ts
    _bias_times: List[pd.Timestamp] = field(default_factory=list)
    _bias_vals: List[float] = field(default_factory=list)

    # ------------------------------------------------------------------ build
    @classmethod
    def precompute(
        cls,
        entry_df: pd.DataFrame,
        htf_df: Optional[pd.DataFrame] = None,
    ) -> "AtozSignals":
        sig = cls(entry_df=entry_df)
        n = len(entry_df)

        # ST model (ep 22-23)
        try:
            from atoz.st_model import find_st_setups
            for s in find_st_setups(entry_df):
                sig.st_dir[int(s.index)] = s.direction.value
        except Exception:
            pass

        # FVG secret story sweep/run (ep 24)
        try:
            from atoz.fvg_story import sweep_run_signals
            for r in sweep_run_signals(entry_df):
                idx = int(getattr(r, "resolve_index", None) or getattr(r, "take_index"))
                sig.sweep_run[idx] = (r.story.value, bool(r.targets_opposing))
        except Exception:
            pass

        # Consolidation (ep 27)
        try:
            from atoz.fvg_story import find_consolidations
            mask = np.zeros(n, dtype=bool)
            for c in find_consolidations(entry_df):
                a = max(0, int(c.start_index)); b = min(n - 1, int(c.end_index))
                if b >= a:
                    mask[a:b + 1] = True
            sig.consolidation_mask = mask
        except Exception:
            sig.consolidation_mask = np.zeros(n, dtype=bool)

        # Dealing ranges (ep 20-21)
        try:
            from atoz.dealing_range import find_dealing_ranges
            drs = find_dealing_ranges(entry_df)
            sig.dealing_ranges = sorted(drs, key=lambda d: int(d.index))
        except Exception:
            pass

        # Turtle soup (ep 28)
        try:
            from atoz.turtle_soup import find_seek_and_destroy, find_strength_weakness
            for s in find_seek_and_destroy(entry_df):
                sig.seek_destroy[int(s.index)] = s.direction.value
                sig.quadrant_at[int(s.index)] = getattr(s.quadrant, "value", "")
            for s in find_strength_weakness(entry_df):
                sig.strength_weak[int(s.index)] = s.direction.value
                sig.quadrant_at.setdefault(int(s.index), getattr(s.quadrant, "value", ""))
        except Exception:
            pass

        # Tiered structure (ep 32)
        try:
            from atoz.turtle_soup import tier_swings
            for t in tier_swings(entry_df):
                si = int(t.swing.index)
                tier_name = getattr(t.tier, "value", "")
                sig.tier_at[si] = (tier_name, bool(t.has_leg_fvg), bool(t.protected))
                if tier_name == "intermediate_term":
                    sig.intermediate_bars.add(si)
        except Exception:
            pass

        # Killzone plans (ep 29-30) — run on the entry tf
        try:
            from atoz.killzone_plans import find_london_setups, find_new_york_setups
            for s in find_london_setups(entry_df):
                idx = int(getattr(s.entry, "index", -1))
                if idx >= 0:
                    sig.session_setup[idx] = ("london", s.variation.value, s.direction.value)
            for s in find_new_york_setups(entry_df):
                idx = int(getattr(s.entry, "index", -1))
                if idx >= 0:
                    sig.session_setup[idx] = ("new_york", s.variation.value, s.direction.value)
        except Exception:
            pass

        # MMXM HTF daily bias (ep 36) — leak-safe series.
        # daily_bias_series is ~O(n^2): slice the HTF down to just the span the
        # entry window needs (entry start back-buffered) before computing it, or
        # a full-history HTF would make this pass take tens of minutes.
        if htf_df is not None and n > 0:
            try:
                from atoz.mmxm import daily_bias_series
                entry_start = entry_df.index[0]
                # ~60-bar HTF lookback before the entry window for context
                htf_pos = htf_df.index.searchsorted(entry_start)
                htf_slice = htf_df.iloc[max(0, htf_pos - 60):]
                series = daily_bias_series(htf_slice)
                m = {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0}
                for ts, bias in series:
                    sig._bias_times.append(pd.Timestamp(ts))
                    sig._bias_vals.append(m.get(bias.value, 0.0))
            except Exception:
                pass

        return sig

    # ---------------------------------------------------------------- lookups
    def _mmxm_bias_at(self, bar_time: pd.Timestamp) -> float:
        """Most recent HTF bias strictly before the bar's calendar day."""
        if not self._bias_times:
            return 0.0
        cutoff = bar_time.normalize()  # midnight of the entry bar's day
        i = bisect.bisect_left(self._bias_times, cutoff)
        return self._bias_vals[i - 1] if i > 0 else 0.0

    def _dealing_range_at(self, bar_idx: int):
        """The most recent dealing range established at or before ``bar_idx``."""
        if not self.dealing_ranges:
            return None
        lo, hi, found = 0, len(self.dealing_ranges) - 1, None
        while lo <= hi:
            mid = (lo + hi) // 2
            if int(self.dealing_ranges[mid].index) <= bar_idx:
                found = self.dealing_ranges[mid]
                lo = mid + 1
            else:
                hi = mid - 1
        return found

    # ----------------------------------------------------------------- extract
    def extract(
        self,
        bar_idx: int,
        direction: Optional[MmcDirection] = None,
    ) -> np.ndarray:
        df = self.entry_df
        bar_time = df.index[bar_idx]
        hour = bar_time.hour
        close = float(df["close"].iloc[bar_idx])
        f: Dict[str, float] = {k: 0.0 for k in ATOZ_FEATURE_NAMES}

        # tally for the LP/HP meta-feature
        bull_args = 0
        bear_args = 0

        def _vote(d):
            nonlocal bull_args, bear_args
            if d == "bullish":
                bull_args += 1
            elif d == "bearish":
                bear_args += 1

        # -- Silver Bullet window (ep 33)
        f["az_silver_bullet"] = float(any(a <= hour < b for a, b in _SB_WINDOWS_BROKER))

        # -- Killzone plan setups (ep 29-30)
        ss = self.session_setup.get(bar_idx)
        if ss is not None:
            session, variation, sdir = ss
            if session == "london":
                f["az_london_setup"] = 1.0
            elif session == "new_york":
                f["az_ny_setup"] = 1.0
            f["az_session_reversal"] = float(variation == "reversal")
            _vote(sdir)

        # -- FVG secret story (ep 24)
        sr = self.sweep_run.get(bar_idx)
        if sr is not None:
            story, targets_opp = sr
            f["az_sweep"] = float(story == "sweep")
            f["az_run"] = float(story == "run")
            f["az_targets_opposing"] = float(targets_opp)

        # -- ST model (ep 22-23)
        st = self.st_dir.get(bar_idx)
        if st is not None:
            f["az_st_present"] = 1.0
            if direction is not None:
                f["az_st_dir_match"] = float(
                    (st == "bullish") == (direction is MmcDirection.BULLISH)
                )
            _vote(st)

        # -- Dealing range / DOL (ep 20-21)
        dr = self._dealing_range_at(bar_idx)
        if dr is not None and dr.high > dr.low:
            rng = dr.high - dr.low
            eq = (dr.high + dr.low) / 2.0
            f["az_in_premium"] = float(close > eq)
            f["az_in_discount"] = float(close < eq)
            # OTE 0.62-0.79 retracement band, oriented by range direction
            if dr.direction.value == "bullish":
                ote_lo, ote_hi = dr.low + 0.21 * rng, dr.low + 0.38 * rng
                dol = dr.high + rng                      # -1.0 symmetrical DOL above
            else:
                ote_lo, ote_hi = dr.high - 0.38 * rng, dr.high - 0.21 * rng
                dol = dr.low - rng                       # -1.0 symmetrical DOL below
            f["az_in_ote"] = float(ote_lo <= close <= ote_hi)
            f["az_dol_distance"] = float(np.clip((dol - close) / rng, -3.0, 3.0) / 3.0)

        # -- MMXM daily bias (ep 36)
        bias = self._mmxm_bias_at(bar_time)
        f["az_mmxm_bias"] = bias
        if direction is not None and bias != 0.0:
            want = 1.0 if direction is MmcDirection.BULLISH else -1.0
            f["az_mmxm_bias_match"] = float(bias == want)
        if bias > 0:
            _vote("bullish")
        elif bias < 0:
            _vote("bearish")

        # -- live entry-tf lag strength (ep 36)
        f["az_lag_strong"] = self._lag_strong(bar_idx)

        # -- Turtle soup (ep 28)
        sd = self.seek_destroy.get(bar_idx)
        if sd is not None:
            f["az_seek_destroy"] = 1.0
            _vote(sd)
        sw = self.strength_weak.get(bar_idx)
        if sw is not None:
            f["az_strength_weakness"] = 1.0
            _vote(sw)
        q = self.quadrant_at.get(bar_idx, "")
        f["az_double_quadrant"] = float(q in ("premium_premium", "discount_discount"))

        # -- Market-structure secrets (ep 32)
        f["az_intermediate"] = float(bar_idx in self.intermediate_bars)
        tier = self.tier_at.get(bar_idx)
        if tier is not None:
            _, has_leg_fvg, protected = tier
            f["az_tier_protected"] = float(has_leg_fvg or protected)

        # -- Consolidation (ep 27)
        if self.consolidation_mask is not None and bar_idx < len(self.consolidation_mask):
            f["az_consolidating"] = float(self.consolidation_mask[bar_idx])

        # -- Power of 3 / Judas (ep 18-19)
        f["az_manipulation"] = self._in_manipulation(bar_idx, direction)

        # -- LP vs HP meta (ep 26): HP only when arguments are 100% one-sided
        if bull_args + bear_args > 0:
            f["az_hp_condition"] = float((bull_args > 0) != (bear_args > 0))

        return np.array([f[k] for k in ATOZ_FEATURE_NAMES], dtype=np.float32)

    # ------------------------------------------------------- per-bar helpers
    def _lag_strong(self, bar_idx: int, look_back: int = 20) -> float:
        """ep 36: the live impulse lag is STRONG if it carries an FVG."""
        try:
            from atoz.mmxm import classify_lag, LagStrength
            start = max(0, bar_idx - look_back)
            sub = self.entry_df.iloc[start:bar_idx + 1].reset_index(drop=True)
            sw = az_find_swings(sub)
            if len(sw) < 2:
                return 0.0
            fvgs = az_find_fvgs(sub)
            lag = classify_lag(sw[-2], sw[-1], fvgs)
            return float(lag.strength is LagStrength.STRONG)
        except Exception:
            return 0.0

    def _in_manipulation(self, bar_idx: int, direction, window: int = 12) -> float:
        """ep 18-19: is this bar inside the Judas/manipulation leg of its session?"""
        try:
            from atoz.profiles import find_judas_swing
            start = max(0, bar_idx - window)
            sub = self.entry_df.iloc[start:bar_idx + 1].reset_index(drop=True)
            az_dir = (
                AzDirection.BULLISH
                if direction is MmcDirection.BULLISH
                else AzDirection.BEARISH
            ) if direction is not None else AzDirection.BULLISH
            js = find_judas_swing(sub, 0, az_dir, window=window)
            if js is None:
                return 0.0
            # in manipulation when the bar sits between the session open and the
            # reversal (price still on the fake side)
            return float(js.fake_extreme_index <= (len(sub) - 1) <= js.reversal_index + 1)
        except Exception:
            return 0.0

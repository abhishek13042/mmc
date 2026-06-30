"""SMT — Smart Money Technique (A-Z Guide ep 13).

> SMT needs two **closely correlated** instruments (ES/NQ, or EURUSD/GBPUSD).
> Bullish SMT = a **crack in correlation** at a low: one makes a lower low while
> the other makes a higher low (they should move in sync but don't). Bearish SMT
> is the mirror at a high. SMT is a **confirmation** tool used *after* you have a
> bias + PD array — never a bias tool on its own. Enter via "buying on strength":
> the candle that swept the low, once its high is taken (a turtle soup).  — ep 13
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pandas as pd

from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Swing, SwingType


class SMTType(Enum):
    BULLISH = "bullish"   # divergence at the lows
    BEARISH = "bearish"   # divergence at the highs


@dataclass
class SMTSignal:
    kind: SMTType
    primary_index: int
    primary_price: float
    corr_price: float


def find_smt(
    primary_df: pd.DataFrame,
    corr_df: pd.DataFrame,
    align: bool = True,
) -> List[SMTSignal]:
    """Detect SMT divergences between two correlated instruments (ep 13).

    Compares consecutive swing lows (bullish SMT) and highs (bearish SMT): a
    signal fires when the primary and correlated instruments disagree on
    direction (one higher, the other lower). Either instrument can be the one
    making the higher/lower swing — the transcript explicitly states "it could
    have very well been the other way around... as long as they are not moving
    in sync" (ep 13).

    ``align`` matches each primary swing to the nearest-in-time correlated swing
    of the same side, within ``align_window`` bars, so that we compare swings
    that are contemporaneous rather than always taking the last-seen correlated
    swing (which can produce false positives when the correlated chart has fewer
    swings between the primary pair).
    """
    p_sw = find_swings(primary_df)
    c_sw = find_swings(corr_df)

    out: List[SMTSignal] = []
    out += _diverge(primary_df, corr_df, swing_lows(p_sw), c_sw, SwingType.LOW, SMTType.BULLISH, align)
    out += _diverge(primary_df, corr_df, swing_highs(p_sw), c_sw, SwingType.HIGH, SMTType.BEARISH, align)
    out.sort(key=lambda s: s.primary_index)
    return out


def _nearest_corr_swing(
    corr_df: pd.DataFrame,
    corr_swings: List[Swing],
    when: pd.Timestamp,
    kind: SwingType,
    window_bars: int = 10,
) -> Optional[float]:
    """Price of the correlated swing of ``kind`` nearest in time to ``when``.

    Searches within ±``window_bars`` of the primary swing's timestamp.  This
    avoids the stale-swing problem of a simple "at or before" lookup: if the
    correlated chart has no new swing between two consecutive primary swings,
    the old "last seen" approach returns the same swing for both endpoints and
    always reports c_higher=False, which either generates phantom divergences or
    silently swallows real ones.
    """
    cands_by_dist = sorted(
        [s for s in corr_swings if s.kind is kind],
        key=lambda s: abs((corr_df.index[s.index] - when).total_seconds()),
    )
    if not cands_by_dist:
        return None
    nearest = cands_by_dist[0]
    # reject if the nearest swing is too far away in calendar time
    # (use the median bar timedelta × window_bars as a guard)
    if len(corr_df) > 1:
        step = (corr_df.index[-1] - corr_df.index[0]) / (len(corr_df) - 1)
        if abs((corr_df.index[nearest.index] - when).total_seconds()) > step.total_seconds() * window_bars:
            return None
    return nearest.price


def _diverge(primary_df, corr_df, p_points, c_sw, kind, smt_type, align) -> List[SMTSignal]:
    out: List[SMTSignal] = []
    for a, b in zip(p_points, p_points[1:]):
        # primary direction between the two consecutive swings
        p_higher = b.price > a.price   # True = higher high/low, False = lower

        if not align:
            continue

        t_a = primary_df.index[a.index]
        t_b = primary_df.index[b.index]

        # Find the correlated swing nearest in time to each primary swing.
        # Using "nearest" rather than "at or before" prevents the same correlated
        # swing being returned for both t_a and t_b when corr has fewer swings,
        # which would incorrectly report c_higher=False always.
        ca = _nearest_corr_swing(corr_df, c_sw, t_a, kind)
        cb = _nearest_corr_swing(corr_df, c_sw, t_b, kind)
        if ca is None or cb is None:
            continue
        if ca == cb:
            # Same correlated swing matched both primary swings — no information
            continue

        c_higher = cb > ca

        # Divergence = the two instruments disagree on direction (ep 13):
        # "it could have very well been the other way around... as long as they
        # are not moving in sync the swing lows are not lining up perfectly"
        # → fire for ANY divergence, regardless of which side is higher.
        if p_higher != c_higher:
            out.append(SMTSignal(smt_type, b.index, b.price, cb))

    return out

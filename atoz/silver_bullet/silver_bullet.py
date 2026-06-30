"""The Silver Bullet entry — WHEN and WHERE to enter (A-Z Guide ep 33).

The instructor gives an *explicit* mechanical recipe for the Silver Bullet:

> "if you always want to trade a silver bullet entry, then a mechanical step
> for that would be is you have your intermediate term high, you have your
> intermediate term low aka your target. That is your context. Then ... drawing
> the swing rate. You wait for the **0.75 level** to be hit and you **enter on
> the first fair value gap** that you can see. And that's it. Target
> intermediate term low. That is your silver bullet entry."  — ep 33

Characteristics of the 0.75 level that shape the trade:

> "the 0.75 level you are not expecting a huge retracement you're expecting a
> sting into a fair value gap and then we continue lower ... it usually is close
> to the drawn liquidity so to make the rr worth it you can indeed have a more
> **aggressive stop loss** ... above the short term high."  — ep 33

So mechanically, per intermediate-term range (the context):

  1. Draw swing rates ITH→ITL (bearish) / ITL→ITH (bullish).
  2. Wait for price to reach (cross) the **0.75** swing rate.
  3. The **first FVG** after that cross, in the direction of the range, is the
     entry (enter at the FVG edge nearest the draw on liquidity = the "sting").
  4. **Stop** above the short-term high (bearish) / below the short-term low
     (bullish) that formed at the 0.75 sting — an aggressive stop.
  5. **Target** = the intermediate-term low / high (the terminus, 1.0).

This is intentionally the *0.75-only* mechanical plan the instructor says to
"pick one ... master it ... stick to it". ``window`` confines the FVG search and
optionally the killzone (the Silver Bullet is a *time* window — ep 33 ties the
0.75 entry to the same NY killzones used in ep 31, see ``silver_bullet_window``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from atoz.core.fvg import FVG, find_fvgs
from atoz.core.swings import find_swings
from atoz.core.types import Candles, Direction, Swing, SwingType
from atoz.timing.killzones import NY_TO_BROKER

from .swing_rates import SwingRate, TermRange, find_term_ranges

# ICT Silver Bullet windows are defined in NY local time. The classic SB is the
# AM 10:00-11:00 NY and the PM 14:00-15:00 NY (plus a London 03:00-04:00 NY).
# ep 33 itself anchors the 0.75 entry to the same NY killzones as ep 31
# (09:30 equities open / NY AM). Broker (EET) = NY + 7 constant.
#
# SILVER_BULLET_WINDOWS_NY is a list of window names in order; it is sliceable
# (``SILVER_BULLET_WINDOWS_NY[:2]``) and each element can be passed to
# ``silver_bullet_window_broker`` to get the corresponding broker-time tuple.
SILVER_BULLET_WINDOWS_NY: list = ["london", "am", "pm"]

# Internal mapping of window-name → (NY_start_hour, NY_end_hour).
_SB_WINDOWS_NY_HOURS = {
    "london": (3.0, 4.0),    # 03:00-04:00 NY  → 10:00-11:00 broker EET
    "am":     (10.0, 11.0),  # 10:00-11:00 NY  → 17:00-18:00 broker EET
    "pm":     (14.0, 15.0),  # 14:00-15:00 NY  → 21:00-22:00 broker EET
}


def silver_bullet_window_broker(name: str = "am") -> tuple:
    """Return a Silver Bullet window in broker (EET) hours = NY + 7 (ep 33).

    Broker time = NY + 7 (constant offset). The three canonical windows:
      london → 03:00-04:00 NY = 10:00-11:00 EET
      am     → 10:00-11:00 NY = 17:00-18:00 EET
      pm     → 14:00-15:00 NY = 21:00-22:00 EET
    """
    s, e = _SB_WINDOWS_NY_HOURS[name]
    return ((s + NY_TO_BROKER) % 24, (e + NY_TO_BROKER) % 24)


@dataclass
class SilverBulletSetup:
    """A 0.75-swing-rate Silver Bullet entry (ep 33)."""

    direction: Direction
    context: TermRange          # the intermediate-term range (ITH→ITL etc.)
    entry_price: float          # first FVG edge after the 0.75 cross (the sting)
    stop_loss: float            # above the ST high (short) / below ST low (long)
    target: float               # the terminus = intermediate-term low / high
    fvg: FVG                    # the "first fair value gap" entered on
    cross_index: int            # bar where price crossed the 0.75 level
    index: int                  # bar the entry FVG confirms (its c3)
    time: Optional[pd.Timestamp] = None
    window: Optional[str] = None

    @property
    def rr(self) -> float:
        risk = abs(self.entry_price - self.stop_loss)
        return abs(self.target - self.entry_price) / risk if risk else 0.0


def _short_term_extreme_near(
    c: Candles, start: int, end: int, direction: Direction
) -> Optional[float]:
    """The short-term high (bearish) / low (bullish) over [start, end] — the
    level the aggressive stop goes beyond (ep 33)."""
    if start > end or start < 0 or end >= c.n:
        return None
    if direction is Direction.BEARISH:
        return float(c.high[start:end + 1].max())
    return float(c.low[start:end + 1].min())


def find_silver_bullet_setups(
    df: pd.DataFrame,
    swings: Optional[List[Swing]] = None,
    strength: int = 2,
    confirm_window: int = 20,
    require_window: Optional[str] = None,
    broker_time: bool = True,
) -> List[SilverBulletSetup]:
    """Detect Silver Bullet (0.75 swing-rate) entries (ep 33).

    For every intermediate-term range, find the bar where price first crosses
    the 0.75 swing rate, then take the **first FVG** in the range's direction
    within ``confirm_window`` bars of that cross as the entry. Stop is beyond the
    short-term extreme between the cross and the FVG; target is the terminus.

    ``require_window`` (one of ``silver_bullet.silver_bullet.SILVER_BULLET_WINDOWS_NY``)
    restricts the *cross* to a NY Silver Bullet time window (converted to broker
    via +7 when ``broker_time``). ``None`` = no time filter (pure 0.75 mechanic).
    """
    c = Candles.of(df)
    if swings is None:
        swings = find_swings(df, strength=strength)
    fvgs = find_fvgs(df)
    ranges = find_term_ranges(df, swings=swings, strength=strength)

    win_bounds = None
    if require_window is not None:
        win_bounds = (
            silver_bullet_window_broker(require_window)
            if broker_time
            else _SB_WINDOWS_NY_HOURS[require_window]
        )

    out: List[SilverBulletSetup] = []
    for ctx in ranges:
        # 1) wait for the 0.75 swing-rate to be hit, after the range is formed
        cross_at = None
        for k in range(ctx.target_index + 1, c.n):
            price = c.low[k] if ctx.direction is Direction.BEARISH else c.high[k]
            if ctx.crossed(price, SwingRate.THREE_QUARTER.value):
                cross_at = k
                break
        if cross_at is None:
            continue

        # optional Silver Bullet time-window filter on the cross
        if win_bounds is not None:
            t = df.index[cross_at]
            h = t.hour + t.minute / 60.0
            s, e = win_bounds
            inside = (s <= h < e) if s <= e else (h >= s or h < e)
            if not inside:
                continue

        # 2) the FIRST fvg in the range direction after the cross
        first = next(
            (
                f for f in fvgs
                if f.direction is ctx.direction
                and cross_at <= f.index <= cross_at + confirm_window
            ),
            None,
        )
        if first is None:
            continue

        # 3) entry at the FVG edge nearest the draw on liquidity (the "sting")
        if ctx.direction is Direction.BEARISH:
            entry_price = first.top          # sell back into the bearish FVG
        else:
            entry_price = first.bottom       # buy back into the bullish FVG

        # 4) aggressive stop beyond the short-term extreme of the sting
        stop = _short_term_extreme_near(c, cross_at, first.c3_index, ctx.direction)
        if stop is None or abs(entry_price - stop) < 1e-12:
            continue

        out.append(
            SilverBulletSetup(
                direction=ctx.direction,
                context=ctx,
                entry_price=float(entry_price),
                stop_loss=float(stop),
                target=float(ctx.target),
                fvg=first,
                cross_index=cross_at,
                index=first.c3_index,
                time=df.index[first.c3_index],
                window=require_window,
            )
        )

    out.sort(key=lambda s: s.index)
    return out

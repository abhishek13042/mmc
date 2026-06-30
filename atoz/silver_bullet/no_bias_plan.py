"""Simple + Effective Trading Plan — No Daily Bias needed (A-Z Guide ep 31).

The instructor's own step list:

> "i'm using the one hour time frame. on the one hour time frame i'm using
> intermediate term highs and intermediate term lows and in between that short
> term highs short term lows. then i'm using time to my advantage ... once we hit
> a one hour pd ray i go into the one minute or the five minute."  — ep 31

No daily bias is required because **structure gives direction**:

> "just based off of the one hour intermediate term highs we can see that
> structure is bearish so price is telling us it wants to go lower."  — ep 31

The target is the obvious drawn liquidity = the intermediate-term low (bearish):

> "the obvious drawn liquidity is ... it's that intermediate term low that is our
> first target."  — ep 31

WHEN — a killzone must bring price into the 1H PD array:

> "with time i mean kill zones so that is your 8 30 that is your 9 30 that is
> your london kill zone that is your new york am session your new york pm
> session. when these kill zones start they will have a fake move ... it will
> move into a premium array then it will show on the lower time frame an entry
> pattern."  — ep 31

The 08:30 / 09:30 rule:

> "if 8 30 already comes into your pd ray and already displaces away from the pd
> ray then 9 30 will likely not take out whatever 8 30 already created."  — ep 31

WHERE — the LTF entry pattern:

> "on a one minute ... you want to have a one minute fair value gap lower then
> after that another one minute fair value gap lower and once you have that
> SECOND fair value gap lower that is exactly when you want to get involved ...
> if you go up in timeframes and you use a five minute entry pattern then you
> only need ONE five minute fair value gap."  — ep 31

Stop = the short-term high that should hold to target; target = the 1H ITL:

> "you can cover that high ... that is a short-term high that should hold until
> we reach the target of this intermediate term low."  — ep 31

This module operates on a single entry-timeframe DataFrame (1m or 5m). The 1H
"PD array" and intermediate-term context are supplied as a ``TermRange`` (build
it from a 1H df via ``swing_rates.find_term_ranges`` or pass the 1H FVG band).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pandas as pd

from atoz.core.fvg import FVG, find_fvgs
from atoz.core.swings import find_swings
from atoz.core.types import Candles, Direction, Swing, SwingType
from atoz.timing.killzones import Killzone, NY_TO_BROKER, killzone_of_broker, killzone_of

from .swing_rates import TermRange


class EntryPattern(Enum):
    """The two LTF entry patterns (ep 31)."""

    ONE_MINUTE = "one_minute"   # need TWO consecutive FVGs
    FIVE_MINUTE = "five_minute" # need ONE FVG


# the killzones the instructor names (NY local hours) — "8 30 ... 9 30 ...
# london ... new york am ... new york pm". 08:30/09:30 are the indices macros.
PLAN_KILLZONES_NY = {
    "macro_830": (8.5, 9.5),
    "equities_open_930": (9.5, 10.0),
    "london": (2.0, 5.0),
    "ny_am": (7.0, 10.0),
    "ny_pm": (13.5, 16.0),
}


def _in_killzone(t: pd.Timestamp, broker_time: bool) -> bool:
    """True if ``t`` falls in any plan killzone (ep 31)."""
    h = t.hour + t.minute / 60.0
    if broker_time:
        h = (h - NY_TO_BROKER) % 24   # convert broker→NY for comparison
    return any(s <= h < e for s, e in PLAN_KILLZONES_NY.values())


@dataclass
class NoBiasSetup:
    """A No-Daily-Bias plan entry (ep 31)."""

    direction: Direction         # from 1H structure (no prediction needed)
    pattern: EntryPattern
    entry_price: float           # the (last) FVG edge entered on
    stop_loss: float             # the short-term high (short) / low (long)
    target: float                # the 1H intermediate-term low / high
    fvgs: List[FVG]              # 1 (5m) or 2 (1m) FVGs that triggered
    pd_array: TermRange          # the 1H context whose PD array we stung into
    index: int                   # confirming bar (last FVG c3)
    time: pd.Timestamp

    @property
    def rr(self) -> float:
        risk = abs(self.entry_price - self.stop_loss)
        return abs(self.target - self.entry_price) / risk if risk else 0.0


def find_no_bias_setups(
    entry_df: pd.DataFrame,
    context: TermRange,
    pattern: EntryPattern = EntryPattern.FIVE_MINUTE,
    require_killzone: bool = True,
    broker_time: bool = True,
    max_gap_bars: int = 6,
    enforce_830_rule: bool = True,
) -> List[NoBiasSetup]:
    """Detect No-Daily-Bias entries on the entry timeframe (1m or 5m) — ep 31.

    Direction comes from ``context`` (built from 1H structure: bearish if the 1H
    intermediate-term highs are holding). Inside a killzone, after price stings
    into the 1H PD array (the context's premium/discount, here approximated by
    price reaching past 0.5 equilibrium toward the origin), we look for the LTF
    entry pattern:

      * ``FIVE_MINUTE`` — one FVG in the range direction.
      * ``ONE_MINUTE``  — two consecutive FVGs in the range direction within
        ``max_gap_bars`` of each other; the SECOND is the entry.

    Stop = the short-term high/low formed in the sting; target = the 1H ITL/ITH.
    ``enforce_830_rule``: skip a 09:30 trigger if 08:30 already displaced away
    from the PD array earlier the same day.
    """
    c = Candles.of(entry_df)
    fvgs = [f for f in find_fvgs(entry_df) if f.direction is context.direction]
    direction = context.direction

    need_two = pattern is EntryPattern.ONE_MINUTE
    out: List[NoBiasSetup] = []

    i = 0
    while i < len(fvgs):
        f1 = fvgs[i]
        t = entry_df.index[f1.c3_index]

        if require_killzone and not _in_killzone(t, broker_time):
            i += 1
            continue

        if enforce_830_rule and _violates_830_rule(entry_df, f1.c3_index, direction, broker_time):
            i += 1
            continue

        chosen: List[FVG]
        if need_two:
            # the SECOND consecutive same-direction FVG is the entry (ep 31)
            if i + 1 >= len(fvgs):
                break
            f2 = fvgs[i + 1]
            if f2.index - f1.c3_index > max_gap_bars:
                i += 1
                continue
            chosen = [f1, f2]
            entry_fvg = f2
        else:
            chosen = [f1]
            entry_fvg = f1

        # entry at the FVG edge nearest the draw on liquidity
        entry_price = entry_fvg.top if direction is Direction.BEARISH else entry_fvg.bottom

        # stop = the short-term high/low across the sting (start of pattern → entry)
        s_idx, e_idx = chosen[0].c1_index, entry_fvg.c3_index
        if direction is Direction.BEARISH:
            stop = float(c.high[s_idx:e_idx + 1].max())
        else:
            stop = float(c.low[s_idx:e_idx + 1].min())

        if abs(entry_price - stop) < 1e-12:
            i += len(chosen)
            continue

        out.append(
            NoBiasSetup(
                direction=direction,
                pattern=pattern,
                entry_price=float(entry_price),
                stop_loss=stop,
                target=float(context.target),
                fvgs=chosen,
                pd_array=context,
                index=entry_fvg.c3_index,
                time=entry_df.index[entry_fvg.c3_index],
            )
        )
        i += len(chosen)

    return out


def _violates_830_rule(
    entry_df: pd.DataFrame, bar: int, direction: Direction, broker_time: bool
) -> bool:
    """The 08:30/09:30 rule (ep 31): if the trigger is at ~09:30 and 08:30 the
    same day already displaced *away* from the PD array (a same-direction FVG
    before 09:00 NY), the 09:30 move "will likely not take out whatever 08:30
    created" — so skip it.
    """
    t = entry_df.index[bar]
    h_ny = ((t.hour + t.minute / 60.0) - (NY_TO_BROKER if broker_time else 0)) % 24
    if not (9.5 <= h_ny < 10.0):
        return False   # rule only governs the 09:30 trigger

    day = t.normalize()
    fvgs = find_fvgs(entry_df)
    for f in fvgs:
        ft = entry_df.index[f.c3_index]
        if ft.normalize() != day:
            continue
        fh_ny = ((ft.hour + ft.minute / 60.0) - (NY_TO_BROKER if broker_time else 0)) % 24
        if 8.5 <= fh_ny < 9.0 and f.direction is direction:
            return True   # 08:30 already displaced away in our direction
    return False

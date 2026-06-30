"""The entry model (A-Z Guide ep 12 — Advanced Entries).

> Step-by-step (fractal): price sweeps a swing low (a liquidity pool) at a HTF
> discount array → it should not stay below long → it **displaces back above**
> the swing, and we objectify "displacement" as a **fair value gap** in the leg
> → the FVG (optionally overlapping a block = FLOD) is the **entry**, the swept
> swing (LLOD) is the **stop**, and the target is the next opposing PD array
> (a daily premium for a long). Get involved in the retracement, not the
> expansion.  — ep 12

This ties together: liquidity sweep (ep 7) + displacement FVG (ep 8) +
FLOD/LLOD (ep 9). It is the atoz analogue of a trade signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from atoz.core.fvg import FVG, find_fvgs
from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Candles, Direction, Swing, SwingType


@dataclass
class Entry:
    """An atoz entry signal (ep 12)."""

    direction: Direction
    entry_price: float       # FLOD (FVG edge)
    stop_loss: float         # LLOD (the swept swing)
    take_profit: float       # next opposing PD array
    sweep_swing: Swing
    displacement_fvg: FVG
    index: int               # bar the entry FVG confirms (c3)

    @property
    def rr(self) -> float:
        risk = abs(self.entry_price - self.stop_loss)
        return abs(self.take_profit - self.entry_price) / risk if risk else 0.0


def find_entries(
    df: pd.DataFrame,
    swings: Optional[List[Swing]] = None,
    confirm_window: int = 15,
) -> List[Entry]:
    """Detect sweep→displacement entries (ep 12).

    For each swing low: if a later bar sweeps it and price then displaces back
    above with a bullish FVG (within ``confirm_window`` bars), that FVG is the
    entry, the swing is the stop, and the nearest higher swing high is the
    target. Mirror for swing highs.
    """
    c = Candles.of(df)
    if swings is None:
        swings = find_swings(df)
    fvgs = find_fvgs(df)
    highs = swing_highs(swings)
    lows = swing_lows(swings)

    out: List[Entry] = []

    for sw in swings:
        bullish = sw.kind is SwingType.LOW
        # 1) sweep of the swing
        sweep_at = None
        for k in range(sw.index + 1, c.n):
            if bullish and c.low[k] < sw.price:
                sweep_at = k
                break
            if not bullish and c.high[k] > sw.price:
                sweep_at = k
                break
        if sweep_at is None:
            continue

        # 2) displacement FVG back through the swing, soon after the sweep
        want = Direction.BULLISH if bullish else Direction.BEARISH
        disp = next(
            (f for f in fvgs
             if f.direction is want and sweep_at <= f.index <= sweep_at + confirm_window),
            None,
        )
        if disp is None:
            continue

        # 3) FLOD entry = FVG edge; LLOD stop = the swept swing; target = opposing PD array
        if bullish:
            entry_price = disp.bottom
            stop = sw.price
            targets = [h.price for h in highs if h.index < disp.index and h.price > entry_price]
            tp = min(targets) if targets else entry_price + 2 * (entry_price - stop)
        else:
            entry_price = disp.top
            stop = sw.price
            targets = [l.price for l in lows if l.index < disp.index and l.price < entry_price]
            tp = max(targets) if targets else entry_price - 2 * (stop - entry_price)

        if abs(entry_price - stop) < 1e-9:
            continue

        out.append(
            Entry(
                direction=want, entry_price=float(entry_price), stop_loss=float(stop),
                take_profit=float(tp), sweep_swing=sw, displacement_fvg=disp,
                index=disp.c3_index,
            )
        )

    out.sort(key=lambda e: e.index)
    return out

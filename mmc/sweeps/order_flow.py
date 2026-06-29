"""Order flow sweep (transcript 08, ~13:43 onward).

An **order flow sweep** is an *actual swing low / swing high* that gets swept.
The shape (transcript 08, ~13:47):

1. We have a PD array (FVG / FVA) we expect to continue *from* (e.g. a bullish
   FVG / discount array we expect higher prices from).
2. Price mitigates that array (stings into it) and rejects — but the rejection
   **fails to make a new FVG** in the array's direction. "The strength, the
   intention is not fully there."
3. That failed rejection leaves behind a **swing low** (for a bullish array) /
   **swing high** (for a bearish array) *without* a new FVG.
4. The original FVG is now mitigated — it can be traded into only once, so we
   **drop it from the chart** (transcript 08, ~17:10: "this fair value gap can
   already be deleted ... it becomes just a random box"). What gets swept is the
   swing point left behind, not the mitigated FVG.

So the detector returns the swept swing level + the index of the swing left
behind, with the mitigated array noted for context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from mmc.core import (
    Direction,
    FairValueGap,
    SwingPoint,
    SwingType,
    find_fvgs,
    find_swings,
    mark_mitigation,
)


@dataclass
class OrderFlowSweep:
    """A swing point left behind after a mitigated FVG's rejection failed to make
    a new FVG — that swing is the level to be swept.

    ``direction``    polarity we continue in (the array's direction).
    ``swing``        the swing low (bullish array) / high (bearish array) left
                     behind; this is the actual liquidity that gets swept.
    ``level``        convenience: ``swing.price``.
    ``index``        convenience: ``swing.index``.
    ``mitigated_fvg`` the already-mitigated array that is dropped — kept only for
                     context / explanation (do not trade from it).
    """

    direction: Direction
    swing: SwingPoint
    mitigated_fvg: FairValueGap

    @property
    def level(self) -> float:
        return self.swing.price

    @property
    def index(self) -> int:
        return self.swing.index


def _has_new_fvg(fvgs: List[FairValueGap], direction: Direction, start: int, end: int) -> bool:
    """Did a *new* FVG of ``direction`` confirm in (start, end]?"""
    for f in fvgs:
        if f.direction is direction and start < f.c3_index <= end:
            return True
    return False


def order_flow_sweeps(
    df: pd.DataFrame,
    swings: Optional[List[SwingPoint]] = None,
    fvgs: Optional[List[FairValueGap]] = None,
    window: int = 4,
) -> List[OrderFlowSweep]:
    """Detect order-flow sweeps: swing points left behind by failed rejections
    off a mitigated FVG.

    For each FVG that has been **mitigated**, we look just after its mitigation
    for the opposing swing point it leaves behind (a swing low after a bullish
    FVG, a swing high after a bearish FVG). If the rejection out of that swing
    does **not** create a new FVG in the array's direction within ``window``
    bars, the swing is what gets swept and we record it.
    """
    if swings is None:
        swings = find_swings(df)
    if fvgs is None:
        fvgs = find_fvgs(df)
        mark_mitigation(df, fvgs)
    out: List[OrderFlowSweep] = []

    for f in fvgs:
        if not f.mitigated or f.mitigation_index is None:
            continue

        # The swing left behind opposes the array we expected to continue from:
        # a bullish (discount) array leaves a swing LOW; a bearish array a HIGH.
        left_kind = SwingType.LOW if f.direction is Direction.BULLISH else SwingType.HIGH

        candidates = [
            s
            for s in swings
            if s.kind is left_kind
            and f.mitigation_index - 1 <= s.index <= f.mitigation_index + window
        ]
        if not candidates:
            continue
        # Nearest swing left behind by the sting.
        swing = min(candidates, key=lambda s: abs(s.index - f.mitigation_index))

        # Failed rejection = no NEW same-direction FVG forms after that swing.
        if _has_new_fvg(fvgs, f.direction, swing.index, swing.index + window):
            continue

        out.append(OrderFlowSweep(direction=f.direction, swing=swing, mitigated_fvg=f))

    out.sort(key=lambda s: s.index)
    return out

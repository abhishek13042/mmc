"""Unmitigated opposing PD arrays (transcript 06).

Fair value gaps get created at **unmitigated opposing PD arrays** — resistance
(for a bullish move) or support (for a bearish move) that price has not traded
into yet. "Unmitigated" = not yet traded into; the smallest touch mitigates it.
"Opposing" = the polarity opposite to the move we expect (premium arrays oppose
a bullish move; discount arrays oppose a bearish move).

These are the levels where rejections form and new FVGs are born, so they are
useful context for classifying the resulting FVG (rejection vs perfect vs
breakaway).
"""

from __future__ import annotations

from typing import List, Union

from mmc.core import (
    Direction,
    FairValueGap,
    SwingPoint,
    SwingType,
    unmitigated,
)

# An opposing PD array can be a swing point or an FVG.
PDArray = Union[SwingPoint, FairValueGap]


def opposing_pd_arrays(
    direction: Direction,
    swings: List[SwingPoint],
    fvgs: List[FairValueGap],
) -> List[PDArray]:
    """Return unmitigated PD arrays opposing a move in ``direction``.

    For a bullish move the opposing (premium) arrays are swing highs and bearish
    FVGs; for a bearish move they are swing lows and bullish FVGs (transcript
    06). FVGs are filtered to the unmitigated ones (the smallest touch mitigates
    them); swings are filtered to those not yet swept.
    """
    opposing = direction.opposite

    if direction is Direction.BULLISH:
        opp_swings = [s for s in swings if s.kind is SwingType.HIGH and not s.swept]
    else:
        opp_swings = [s for s in swings if s.kind is SwingType.LOW and not s.swept]

    opp_fvgs = [f for f in unmitigated(fvgs) if f.direction is opposing]

    arrays: List[PDArray] = [*opp_swings, *opp_fvgs]
    arrays.sort(key=lambda a: a.index)
    return arrays

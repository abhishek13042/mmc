"""Full London Killzone Trading Plan (A-Z Guide ep 29).

> "A full trading plan using a London kill zone. ... we have two scenarios ...
>  First, we have an **Asia expansion** and we have an **Asia consolidation**."
>  — ep 29

Both scenarios are the same mechanical plan (see :mod:`atoz.killzone_plans.plan`),
differing only in what Asia did before London opens:

**Asia expansion** (``SessionVariation.EXPANSION``)
    > "if asia already has bearish fair value gaps that is perfectly fine ...
    >  london opens up ... all i need to see in London is a new bearish fair
    >  value gap. I enter on the overlapping PDA ... cover these highs ... your
    >  target again it was that four hour low."  — ep 29
    Asia already displaced in the bias direction; one new London FVG is enough.

**Asia consolidation** (``SessionVariation.CONSOLIDATION``) — the *classic*
London setup:
    > "we need bearish fair value gaps being created in London itself ... you
    >  have a first bearish fair value gap and you wait for a second one ... that
    >  is again your sd model then that right there that is your entry covering
    >  the intermediate term high targeting ... that four hour swing low."  — ep 29

Stop placement (ep 29): cover the intermediate-term high/low that was swept —
``find_entries`` already sets the stop to the swept (LLOD) swing. The instructor
notes you only widen above that high if a 15m/1H FVG sits above giving price a
reason to return; otherwise "Price has no reason to come back there ... you cover
these highs."

The instructor advises this plan for **Forex pairs** specifically:
    > "this trading plan, particularly the London trading plan, I would advise
    >  to focus on Forex pairs."  — ep 29
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

from atoz.core import Direction, Swing
from atoz.timing import Killzone

from .plan import SessionSetup, SessionVariation, find_session_setups


def find_london_setups(
    df: pd.DataFrame,
    bias: Optional[Direction] = None,
    swings: Optional[List[Swing]] = None,
    confirm_window: int = 15,
) -> List[SessionSetup]:
    """Detect Full London Killzone Trading Plan setups (ep 29).

    Returns :class:`SessionSetup` objects whose entry FVG confirms inside the
    London killzone (09:00-12:00 broker/EET time). Each is labelled
    ``SessionVariation.EXPANSION`` (Asia expansion) or
    ``SessionVariation.CONSOLIDATION`` (Asia consolidation / classic London).

    ``bias`` (premium→discount = ``Direction.BEARISH``) is the 4H/HTF bias the
    video sets first; leave ``None`` to take both directions.
    """
    return find_session_setups(
        df,
        session=Killzone.LONDON,
        bias=bias,
        swings=swings,
        confirm_window=confirm_window,
    )


def asia_expansion_setups(
    df: pd.DataFrame,
    bias: Optional[Direction] = None,
    **kwargs,
) -> List[SessionSetup]:
    """London setups of the **Asia expansion** variation only (ep 29)."""
    return [
        s for s in find_london_setups(df, bias=bias, **kwargs)
        if s.variation is SessionVariation.EXPANSION
    ]


def asia_consolidation_setups(
    df: pd.DataFrame,
    bias: Optional[Direction] = None,
    **kwargs,
) -> List[SessionSetup]:
    """London setups of the **Asia consolidation** (classic London) variation
    only (ep 29)."""
    return [
        s for s in find_london_setups(df, bias=bias, **kwargs)
        if s.variation is SessionVariation.CONSOLIDATION
    ]

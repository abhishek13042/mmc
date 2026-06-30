"""Trading Plan for the New York Killzone (A-Z Guide ep 30).

> "a New York strategy for Forex. ... we have two variables ... today we are
>  going to touch on a **new york retracement** and a **new york reversal** ...
>  the new york retracement is the exact same thing as the asia expansion and
>  the new york reversal is the exact same thing as your asia consolidation the
>  only thing that changes is the time."  — ep 30

So the NY plan reuses the shared engine (:mod:`atoz.killzone_plans.plan`) with
the New York killzone window and the variation names mapped:

**New York retracement** (``SessionVariation.EXPANSION``)
    The London-plan "Asia expansion" analogue. London already came into a HTF PD
    array and displaced in the bias direction (London made the low of the day);
    NY then waits for a single new FVG in the bias direction.
    > "London right there is coming into that higher time frame PD ray already.
    >  And London already had what? A displacement higher ... in New York you now
    >  wait for a bullish fair value gap higher ... that right there could already
    >  be your entry ... you cover this low ... your intermediate term low in new
    >  york ... your targets are that high ... your four hour opposing premium
    >  array ... this is the exact same as asia expansion we just called new york
    >  retracement."  — ep 30

**New York reversal** (``SessionVariation.CONSOLIDATION``)
    The London-plan "Asia consolidation" analogue. London did *not* come into the
    HTF PD array (London did not make the low of the day); NY itself comes into
    the HTF PD array and builds the SD model.
    > "this is a new york reversal ... the london low was right there ... london
    >  didn't make the low of the day. If london makes the low of the day and new
    >  york respects that low then you have a new york retracement ... here we have
    >  our st model ... we use overlapping pd race ... cover this low ... your
    >  intermediate term high ... if i mentioned to you that this was london then
    >  this would have been your asia consolidation."  — ep 30

Stop placement (ep 30): place the stop at the swept 5-minute swing (the ITH/ITL
you cover), not wider, unless the timeframe above gives price a reason to return:
    > "place our stop loss at that five minute load that we had right there ...
    >  there's no reason to suffocate ... suffocating your stop loss [is] placing
    >  your stop loss at a place where price still has a reason to come back."
    — ep 30
``find_entries`` already sets the stop to the swept (LLOD) swing.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

from atoz.core import Direction, Swing
from atoz.timing import Killzone

from .plan import SessionSetup, SessionVariation, find_session_setups


def find_new_york_setups(
    df: pd.DataFrame,
    bias: Optional[Direction] = None,
    swings: Optional[List[Swing]] = None,
    confirm_window: int = 15,
) -> List[SessionSetup]:
    """Detect New York Killzone Trading Plan setups (ep 30).

    Returns :class:`SessionSetup` objects whose entry FVG confirms inside the
    New York killzone (14:00-17:00 broker/EET time). Each is labelled
    ``SessionVariation.EXPANSION`` (New York **retracement**) or
    ``SessionVariation.CONSOLIDATION`` (New York **reversal**).

    ``bias`` (premium→discount = ``Direction.BEARISH``) is the monthly/4H HTF
    bias the video sets first; leave ``None`` to take both directions.
    """
    return find_session_setups(
        df,
        session=Killzone.NEW_YORK,
        bias=bias,
        swings=swings,
        confirm_window=confirm_window,
    )


def new_york_retracement_setups(
    df: pd.DataFrame,
    bias: Optional[Direction] = None,
    **kwargs,
) -> List[SessionSetup]:
    """NY setups of the **New York retracement** variation only (ep 30)
    (== the Asia-expansion analogue)."""
    return [
        s for s in find_new_york_setups(df, bias=bias, **kwargs)
        if s.variation is SessionVariation.EXPANSION
    ]


def new_york_reversal_setups(
    df: pd.DataFrame,
    bias: Optional[Direction] = None,
    **kwargs,
) -> List[SessionSetup]:
    """NY setups of the **New York reversal** variation only (ep 30)
    (== the Asia-consolidation analogue)."""
    return [
        s for s in find_new_york_setups(df, bias=bias, **kwargs)
        if s.variation is SessionVariation.CONSOLIDATION
    ]

"""Order-flow-lag decomposition: FLOD / ODD / LOD (transcript 04).

An order flow lag holds three PD arrays we can trade *from*: the FVG, the FVA
and the swing point. Dissecting the lag (transcript 04):

* **FLOD** (First Line Of Defense) — the first PD array price retraces into.
  Ideally the **FVG** (more bullish/bearish intention => higher probability). The
  worse case is the FVA being the FLOD.
* **ODD** (Overlapping Defense, a.k.a. O-LOD) — the first area where two PD
  arrays overlap. Ideally the **FVA** overlapping the FVG (two discount/premium
  arrays = double probability).
* **LOD** (Last Line Of Defense) — always the **swing point**. The *best* LOD is
  a lag with **no FVG** (the swing is the only thing to trade from). When the lag
  *has* an FVG (a normal order flow lag), the LOD is something to trade *towards*
  (liquidity), not from.

Probability of the lag (transcript 04): **high** when the FLOD is the FVG (the
FVA is the ODD), **low** when the FVA is the FLOD (the FVG is the ODD).
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

from mmc.core import (
    Direction,
    FairValueArea,
    FairValueGap,
    OrderFlowLag,
    SwingPoint,
    Zone,
)


def _retrace_first(a: Zone, b: Zone, direction: Direction) -> bool:
    """True if PD array ``a`` is encountered *before* ``b`` on a retracement.

    A bullish (discount) lag retraces downward from above, so the array with the
    **higher** top is hit first. A bearish (premium) lag retraces upward, so the
    array with the **lower** bottom is hit first.
    """
    if direction is Direction.BULLISH:
        return a.top >= b.top  # higher zone reached first on a down-retrace
    return a.bottom <= b.bottom  # lower zone reached first on an up-retrace


def decompose_lag(
    lag: OrderFlowLag,
    df: Optional[pd.DataFrame] = None,
    fvas: Optional[List[FairValueArea]] = None,
) -> OrderFlowLag:
    """Populate ``lag.flod`` / ``lag.odd`` / ``lag.lod`` (transcript 04).

    If ``lag.fva`` is unset, the nearest same-polarity FVA from ``fvas`` (one
    whose band overlaps the lag's FVG) is attached. The LOD is always the swing
    point. FLOD/ODD are ordered by which PD array a retracement hits first:

    * FVG hit first  -> FLOD = FVG, ODD = FVA   (high probability)
    * FVA hit first  -> FLOD = FVA, ODD = FVG   (low probability)

    When the lag has no FVA, the FVG is both the FLOD and the ODD (the only
    overlap available).
    """
    lag.lod = lag.swing  # LOD is always the swing point (transcript 04)

    fvg = lag.fvg
    fva = lag.fva
    if fva is None and fvas:
        fva = _attach_fva(lag, fvas)
        lag.fva = fva

    if fva is None:
        # No overlapping area: the FVG is the only defense.
        lag.flod = fvg
        lag.odd = fvg
        return lag

    if _retrace_first(fvg, fva, lag.direction):
        lag.flod = fvg
        lag.odd = fva
    else:
        lag.flod = fva
        lag.odd = fvg
    return lag


def _attach_fva(
    lag: OrderFlowLag, fvas: List[FairValueArea]
) -> Optional[FairValueArea]:
    """Pick the same-polarity FVA whose price band overlaps the lag's FVG."""
    fvg = lag.fvg
    matches = [
        a
        for a in fvas
        if a.direction is lag.direction
        and a.bottom <= fvg.top
        and a.top >= fvg.bottom
    ]
    if not matches:
        return None
    return min(matches, key=lambda a: abs(a.index - fvg.index))


def lag_probability(lag: OrderFlowLag) -> str:
    """Rate a lag "high" or "low" by its FLOD (transcript 04).

    High probability when the FLOD is the FVG (the FVA is the ODD): more
    bullish/bearish intention. Low when the FVA is the FLOD (FVG is the ODD): the
    opposing side created a strong retracement. ``decompose_lag`` must run first.

    A lag with **no FVG** is not represented by this function — that is the best
    *LOD* case, handled separately (the swing point is the only array).
    """
    if lag.flod is None:
        decompose_lag(lag)
    if lag.flod is lag.fvg:
        return "high"
    return "low"


def is_seeking_liquidity(lag: OrderFlowLag, df: pd.DataFrame) -> bool:
    """True if price disrespected the FVA and is now seeking the LOD (swing point).

    Transcript 04: the market either offers fair value or seeks liquidity. Once
    an FVA has offered fair value, a *deep* retracement past it means it is no
    longer offering fair value — it is seeking liquidity, which is the swing
    point (the LOD, something to trade *towards*, "unusual context").

    We detect a deep retracement as price trading **beyond** the FVA's far edge
    after the lag confirmed: below ``fva.bottom`` for a bullish lag, above
    ``fva.top`` for a bearish lag.
    """
    fva = lag.fva
    if fva is None:
        return False
    later = df.iloc[lag.index + 1 :]
    if later.empty:
        return False
    if lag.direction is Direction.BULLISH:
        return bool((later["low"] < fva.bottom).any())
    return bool((later["high"] > fva.top).any())


def decompose_lags(
    lags: List[OrderFlowLag],
    df: Optional[pd.DataFrame] = None,
    fvas: Optional[List[FairValueArea]] = None,
) -> List[OrderFlowLag]:
    """Decompose every lag in-place and return the same list for chaining."""
    for lag in lags:
        decompose_lag(lag, df=df, fvas=fvas)
    return lags

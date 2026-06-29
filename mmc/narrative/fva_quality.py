"""Fair Value Area quality classification (transcript 07 — FVAs / order blocks).

Order blocks, mitigation blocks and breaker blocks are all the same thing: the
**fair value area** (FVA), the *overlapping defense* of an order flow lag. FVAs
get created when price takes out a previous swing point. Ranked best -> worst by
strength:

1. **"ideal"** — FVA + an overlapping FVG (sitting exactly on the swept high/low)
   **and** a nested FVA (a smaller FVA just inside the bigger one). Three
   discount/premium arrays = triple probability.
2. **"good"** — FVA + an overlapping FVG, but no nested FVA. Still strong.
3. **"swept"** (worst) — the high/low was swept (wicked) instead of producing an
   overlapping FVG. The FVA becomes the **FLOD** and the FVG the ODD -> lack of
   strength -> avoid.

Modelling:

* **Overlapping FVG** — an FVG of the *same polarity* as the FVA whose price band
  overlaps the swing the FVA was built on (the high for a bearish FVA, the low
  for a bullish FVA). Transcript: "overlapping with the exact high that we took".
* **Nested FVA** — a smaller same-direction FVA fully contained inside this FVA,
  sitting just below (bullish) / above (bearish) the boundary.
* **Swept** — the swing high/low was wicked (a later bar's extreme pierced the
  swing price) without a same-polarity FVG overlapping it. Mirrors the swing
  ``swept`` flag from the sweeps layer; here we also infer it from price.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

from mmc.core import Direction, FairValueArea, FairValueGap, SwingType


def _fva_swing_price(fva: FairValueArea) -> Optional[float]:
    """The price of the swing the FVA was built around (the high for a bearish
    FVA, the low for a bullish FVA — i.e. the boundary that gets swept)."""
    if fva.direction is Direction.BEARISH:
        return fva.top
    return fva.bottom


def find_overlapping_fvg(
    fva: FairValueArea, fvgs: List[FairValueGap]
) -> Optional[FairValueGap]:
    """Return the same-polarity FVG overlapping the FVA's swing boundary, if any.

    The overlapping FVG sits on the exact swing high/low the FVA was created
    from (transcript 07). We require matching direction and a price overlap with
    the swing boundary, picking the nearest such FVG by index.
    """
    boundary = _fva_swing_price(fva)
    if boundary is None:
        return None

    matches = [
        f
        for f in fvgs
        if f.direction is fva.direction and f.bottom <= boundary <= f.top
    ]
    if not matches:
        return None
    # The FVG that confirms the FVA sits at/after the boundary; take the nearest.
    return min(matches, key=lambda f: abs(f.index - fva.index))


def find_nested_fva(
    fva: FairValueArea, fvas: List[FairValueArea]
) -> Optional[FairValueArea]:
    """Return a smaller same-direction FVA nested inside ``fva`` (transcript 07).

    A nested FVA is fully contained within the bigger FVA's price band and is
    strictly smaller, sitting just inside the boundary that was taken.
    """
    candidates = [
        a
        for a in fvas
        if a is not fva
        and a.direction is fva.direction
        and a.size < fva.size
        and a.top <= fva.top
        and a.bottom >= fva.bottom
    ]
    if not candidates:
        return None
    # Prefer the one hugging the swept boundary (largest of the nested ones).
    return max(candidates, key=lambda a: a.size)


def _was_swept(df: pd.DataFrame, fva: FairValueArea) -> bool:
    """True if the FVA's swing boundary was wicked after the FVA confirmed.

    A bearish FVA is swept if a later bar's high pierces ``fva.top``; a bullish
    FVA if a later bar's low pierces ``fva.bottom`` — a wick beyond the swing
    point (transcript 07: "we create that wick above it").
    """
    boundary = _fva_swing_price(fva)
    if boundary is None:
        return False
    later = df.iloc[fva.index + 1 :]
    if later.empty:
        return False
    if fva.direction is Direction.BEARISH:
        return bool((later["high"] > boundary).any())
    return bool((later["low"] < boundary).any())


def classify_fva(
    fva: FairValueArea,
    fvgs: List[FairValueGap],
    fvas: Optional[List[FairValueArea]] = None,
    df: Optional[pd.DataFrame] = None,
) -> str:
    """Set and return ``fva.quality`` -> "ideal" | "good" | "swept".

    Also attaches ``fva.overlapping_fvg`` and ``fva.nested`` when found.

    * If the boundary was swept (wicked) and no same-polarity overlapping FVG
      defends it -> "swept" (the FVA becomes the FLOD).
    * Else, with an overlapping FVG + a nested FVA -> "ideal".
    * Else, with just an overlapping FVG -> "good".
    * A bare swept boundary with no overlapping FVG also falls to "swept".
    """
    overlapping = find_overlapping_fvg(fva, fvgs)
    fva.overlapping_fvg = overlapping

    nested = find_nested_fva(fva, fvas) if fvas else None
    fva.nested = nested

    swept = _was_swept(df, fva) if df is not None else False

    if overlapping is None:
        # No FVG defending the swing boundary: weakest case (swept / FLOD).
        fva.quality = "swept"
    elif swept:
        # Boundary wicked even though an FVG exists -> respecting the swing
        # point => lack of strength => the FVA is the worst to trade from.
        fva.quality = "swept"
    elif nested is not None:
        fva.quality = "ideal"
    else:
        fva.quality = "good"
    return fva.quality


def classify_fvas(
    fvas: List[FairValueArea],
    fvgs: List[FairValueGap],
    df: Optional[pd.DataFrame] = None,
) -> List[FairValueArea]:
    """Classify every FVA in-place (passing the full list for nested detection)."""
    for fva in fvas:
        classify_fva(fva, fvgs, fvas=fvas, df=df)
    return fvas

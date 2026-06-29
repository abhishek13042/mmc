"""MMC narrative layer (transcripts 04, 06, 07).

**Direction** tells us which PD array to trade *towards*; **narrative** tells us
which PD array to trade *from* and how it delivers there. This layer classifies
the quality of the PD arrays inside an order flow lag and dissects the lag into
its three defenses.

Public API
----------
FVG quality (transcript 06)
    ``classify_fvg(df, fvg)`` / ``classify_fvgs(df, fvgs)``
        -> sets ``fvg.quality`` to "rejection" | "perfect" | "breakaway".

FVA quality (transcript 07)
    ``classify_fva(fva, fvgs, fvas=, df=)`` / ``classify_fvas(fvas, fvgs, df=)``
        -> sets ``fva.quality`` to "ideal" | "good" | "swept" and attaches
        ``overlapping_fvg`` / ``nested``.
    ``find_overlapping_fvg`` / ``find_nested_fva`` helpers.

Lag decomposition — FLOD / ODD / LOD (transcript 04)
    ``decompose_lag(lag, df=, fvas=)`` / ``decompose_lags(...)``
        -> populates ``lag.flod`` / ``lag.odd`` / ``lag.lod``.
    ``lag_probability(lag)`` -> "high" | "low".
    ``is_seeking_liquidity(lag, df)`` -> bool (unusual context).

Opposing PD arrays (transcript 06)
    ``opposing_pd_arrays(direction, swings, fvgs)`` — where FVGs get created.
"""

from .fva_quality import (
    classify_fva,
    classify_fvas,
    find_nested_fva,
    find_overlapping_fvg,
)
from .fvg_quality import classify_fvg, classify_fvgs
from .lag import (
    decompose_lag,
    decompose_lags,
    is_seeking_liquidity,
    lag_probability,
)
from .pd_arrays import opposing_pd_arrays

__all__ = [
    # FVG quality (transcript 06)
    "classify_fvg",
    "classify_fvgs",
    # FVA quality (transcript 07)
    "classify_fva",
    "classify_fvas",
    "find_overlapping_fvg",
    "find_nested_fva",
    # Lag decomposition (transcript 04)
    "decompose_lag",
    "decompose_lags",
    "lag_probability",
    "is_seeking_liquidity",
    # Opposing PD arrays (transcript 06)
    "opposing_pd_arrays",
]

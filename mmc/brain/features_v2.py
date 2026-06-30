"""Brain v2 feature set: mmc (31) + atoz (24) = 55 concept features.

v1 learned weights over the 31 features the **mmc** engine produces. v2 keeps all
of those and appends the **atoz** library's concepts (the faithful ICT A-Z Guide
implementation, ep 1-39). The two blocks are concatenated so a single network
sees both knowledge bases and the readable Perceptron weights tell us, per
concept, which library actually carries the edge.

    FEATURE_NAMES_V2 = FEATURE_NAMES (mmc, 31) + ATOZ_FEATURE_NAMES (atoz, 24)

Use :func:`extract_features_v2` exactly like v1's ``extract_features`` but pass a
precomputed :class:`~mmc.brain.atoz_features.AtozSignals` (built once per symbol)
so the atoz detectors don't re-run inside every look-back window.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from mmc.brain.features import FEATURE_NAMES, extract_features
from mmc.brain.atoz_features import ATOZ_FEATURE_NAMES, AtozSignals
from mmc.core import Direction

FEATURE_NAMES_V2 = list(FEATURE_NAMES) + list(ATOZ_FEATURE_NAMES)
N_FEATURES_V2 = len(FEATURE_NAMES_V2)


def extract_features_v2(
    bar_idx: int,
    entry_df: pd.DataFrame,
    atoz_signals: AtozSignals,
    htf_df: Optional[pd.DataFrame] = None,
    corr_df: Optional[pd.DataFrame] = None,
    direction: Optional[Direction] = None,
) -> np.ndarray:
    """Concatenate the mmc (v1) and atoz feature blocks for ``bar_idx``.

    Args:
        bar_idx:       Position in ``entry_df`` to extract at.
        entry_df:      Entry-tf OHLCV with a DatetimeIndex.
        atoz_signals:  Precomputed :class:`AtozSignals` for this ``entry_df``.
        htf_df:        Context-tf DataFrame (HTF bias + mmxm daily bias).
        corr_df:       Correlated instrument (SMT). None → SMT features 0.
        direction:     Candidate direction hint.

    Returns:
        np.ndarray of shape (N_FEATURES_V2,), float32.
    """
    mmc_vec = extract_features(
        bar_idx, entry_df, htf_df=htf_df, corr_df=corr_df, direction=direction
    )
    atoz_vec = atoz_signals.extract(bar_idx, direction=direction)
    return np.concatenate([mmc_vec, atoz_vec]).astype(np.float32)

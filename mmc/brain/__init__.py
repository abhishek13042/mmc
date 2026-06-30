"""MMC Decision Brain — neural network trading decision system.

Built from 11 A-Z lecture transcripts + liquidity masterclass concepts.
Three architectures of increasing complexity:

    Perceptron  → readable concept weights, needs ~300+ setups
    ShallowNN   → learns concept combinations, needs ~1000+ setups
    DeepNN      → deepest reasoning, needs ~3000+ setups

Quick start:
    from mmc.brain import run_brain
    results = run_brain("EURUSD")
"""

from mmc.brain.architectures import DeepNN, Perceptron, ShallowNN, get_model
from mmc.brain.dataset import build_all_datasets, build_dataset
from mmc.brain.features import FEATURE_NAMES, N_FEATURES, extract_features
from mmc.brain.train import compare_architectures, print_feature_importance

# --- Brain v2: mmc + atoz combined feature set --------------------------------
from mmc.brain.atoz_features import ATOZ_FEATURE_NAMES, N_ATOZ_FEATURES, AtozSignals
from mmc.brain.features_v2 import (
    FEATURE_NAMES_V2,
    N_FEATURES_V2,
    extract_features_v2,
)
from mmc.brain.dataset_v2 import build_all_datasets_v2, build_dataset_v2
from mmc.brain.train_v2 import compare_architectures_cols, perceptron_weights


def run_brain(
    symbol: str = "EURUSD",
    verbose: bool = True,
) -> "pd.DataFrame":
    """One-shot v1: build the mmc-feature dataset and compare all 3 architectures."""
    from mmc.core.types import Timeframe

    dataset = build_dataset(symbol, Timeframe.H4, Timeframe.H1, verbose=verbose)
    if dataset.empty:
        raise RuntimeError(f"No setups found for {symbol}. Check data paths.")
    return compare_architectures(dataset, verbose=verbose)


def run_brain_v2(
    symbol: str = "EURUSD",
    limit_bars: int = None,
    verbose: bool = True,
):
    """One-shot v2: build the mmc+atoz dataset and compare all 3 architectures.

    Returns (results_table, trained_perceptron). Read concept weights with
    ``perceptron_weights(perceptron, FEATURE_NAMES_V2)``.
    """
    from mmc.core.types import Timeframe

    dataset = build_dataset_v2(
        symbol, Timeframe.H4, Timeframe.H1, limit_bars=limit_bars, verbose=verbose
    )
    if dataset.empty:
        raise RuntimeError(f"No setups found for {symbol}. Check data paths.")
    return compare_architectures_cols(dataset, feature_cols=FEATURE_NAMES_V2, verbose=verbose)


__all__ = [
    # architectures
    "Perceptron", "ShallowNN", "DeepNN", "get_model",
    # v1
    "build_dataset", "build_all_datasets",
    "extract_features", "FEATURE_NAMES", "N_FEATURES",
    "compare_architectures", "print_feature_importance",
    "run_brain",
    # v2 (mmc + atoz)
    "AtozSignals", "ATOZ_FEATURE_NAMES", "N_ATOZ_FEATURES",
    "extract_features_v2", "FEATURE_NAMES_V2", "N_FEATURES_V2",
    "build_dataset_v2", "build_all_datasets_v2",
    "compare_architectures_cols", "perceptron_weights",
    "run_brain_v2",
]

"""Three neural network architectures for the MMC decision brain.

All three take the same 31-feature input vector and output a single logit
(raw score before sigmoid).  Use BCEWithLogitsLoss for training.

Architecture 1 — Perceptron (transcript reference: ANALYSIS.md perceptron sketch)
    One linear layer.  The weight for each feature IS the brain's opinion of
    how much that concept matters.  Fully interpretable — you can read which
    concept has the highest weight.

Architecture 2 — Shallow NN (1 hidden layer, 32 neurons)
    Learns *combinations* of concepts — e.g. the hidden "sweep node" fires
    when sweep_detected=1 AND in_ny_kz=1 AND htf_bias=-1 all align.
    Cannot be read as directly as the perceptron, but SHAP gives explanations.

Architecture 3 — Deep NN (3 hidden layers: 64→32→16)
    Learns combinations of combinations.  Needs the most data (~5k+ setups).
    Use walk-forward validation to confirm it actually outperforms Shallow NN
    before deploying.

All use Dropout for regularisation (markets are noisy / non-stationary).
"""

from __future__ import annotations

from typing import Dict

import torch
import torch.nn as nn

from mmc.brain.features import N_FEATURES


# ---------------------------------------------------------------------------
# Architecture 1: Perceptron
# ---------------------------------------------------------------------------

class Perceptron(nn.Module):
    """Single linear layer — the simplest possible decision brain.

    The weight vector is directly readable:
        model.linear.weight[0]  → one weight per concept
    Sort by abs(weight) to see which MMC concept the brain values most.
    """

    def __init__(self, n_features: int = N_FEATURES):
        super().__init__()
        self.linear = nn.Linear(n_features, 1)
        nn.init.xavier_uniform_(self.linear.weight)
        nn.init.zeros_(self.linear.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.linear(x)  # raw logit

    def feature_weights(self) -> Dict[str, float]:
        """Return {feature_name: weight} — the brain's opinion of each concept."""
        from mmc.brain.features import FEATURE_NAMES
        w = self.linear.weight.detach().cpu().squeeze().numpy()
        return dict(zip(FEATURE_NAMES, w.tolist()))


# ---------------------------------------------------------------------------
# Architecture 2: Shallow NN (1 hidden layer)
# ---------------------------------------------------------------------------

class ShallowNN(nn.Module):
    """One hidden layer that learns concept *combinations*.

    The hidden neurons are analogs of the human thought process:
        "I see a sweep AND it's NY killzone AND HTF is bearish → now trade."
    Hidden dim = 32 works well for ~500-2000 setups.
    """

    def __init__(self, n_features: int = N_FEATURES, hidden: int = 32):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features, hidden),
            nn.LayerNorm(hidden),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden, 1),
        )
        self._init_weights()

    def _init_weights(self):
        for layer in self.net:
            if isinstance(layer, nn.Linear):
                nn.init.xavier_uniform_(layer.weight)
                nn.init.zeros_(layer.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


# ---------------------------------------------------------------------------
# Architecture 3: Deep NN (3 hidden layers)
# ---------------------------------------------------------------------------

class DeepNN(nn.Module):
    """Three hidden layers that learn combinations of combinations.

    Layer structure mirrors how a human trader thinks in levels:
        Layer 1 (64): raw concept patterns  (is this a sweep? in killzone?)
        Layer 2 (32): setup quality nodes   (this looks like FLOD+sweep+KZ)
        Layer 3 (16): conviction nodes      (high conviction / skip)
        Output   (1): take / skip logit

    Needs ~2000+ labeled setups to outperform ShallowNN reliably.
    Use walk-forward validation before trusting.
    """

    def __init__(self, n_features: int = N_FEATURES):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features, 64),
            nn.LayerNorm(64),
            nn.ReLU(),
            nn.Dropout(0.3),

            nn.Linear(64, 32),
            nn.LayerNorm(32),
            nn.ReLU(),
            nn.Dropout(0.2),

            nn.Linear(32, 16),
            nn.ReLU(),

            nn.Linear(16, 1),
        )
        self._init_weights()

    def _init_weights(self):
        for layer in self.net:
            if isinstance(layer, nn.Linear):
                nn.init.xavier_uniform_(layer.weight)
                nn.init.zeros_(layer.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

ARCHITECTURES = {
    "perceptron": Perceptron,
    "shallow":    ShallowNN,
    "deep":       DeepNN,
}


def get_model(name: str, n_features: int = N_FEATURES) -> nn.Module:
    """Instantiate a model by name: 'perceptron', 'shallow', or 'deep'."""
    if name not in ARCHITECTURES:
        raise ValueError(f"Unknown architecture '{name}'. Choose: {list(ARCHITECTURES)}")
    return ARCHITECTURES[name](n_features)


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)

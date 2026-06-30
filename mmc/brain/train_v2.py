"""Walk-forward training for Brain v2 (feature-column-aware).

Mirrors ``train.py`` but parametrised on the feature columns so it can train on
the 55-feature v2 set (or any subset). The split, embargo, class-weighted BCE,
early stopping and profit-factor evaluation are identical to v1 so the v1↔v2
comparison is apples-to-apples.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from mmc.brain.architectures import ARCHITECTURES, get_model
from mmc.brain.features_v2 import FEATURE_NAMES_V2
from mmc.brain.train import walk_forward_split, evaluate_model


def _prep(df: pd.DataFrame, cols: List[str]) -> Tuple[torch.Tensor, torch.Tensor]:
    X = torch.tensor(df[cols].values, dtype=torch.float32)
    y = torch.tensor(df["label"].values, dtype=torch.float32).unsqueeze(1)
    return X, y


def train_model_cols(
    model: nn.Module,
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    feature_cols: List[str],
    epochs: int = 150,
    lr: float = 1e-3,
    batch_size: int = 64,
    patience: int = 20,
    device: str = "cpu",
) -> Dict:
    model = model.to(device)
    X_tr, y_tr = _prep(train_df, feature_cols)
    X_vl, y_vl = _prep(val_df, feature_cols)
    X_tr, y_tr, X_vl, y_vl = X_tr.to(device), y_tr.to(device), X_vl.to(device), y_vl.to(device)

    n_pos = float(y_tr.sum())
    n_neg = float(len(y_tr) - n_pos)
    pos_weight = torch.tensor([n_neg / max(n_pos, 1)], device=device)

    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=10, factor=0.5, min_lr=1e-5
    )
    loader = DataLoader(TensorDataset(X_tr, y_tr), batch_size=batch_size, shuffle=True)

    best_val, best_state, no_improve = float("inf"), None, 0
    epoch = 0
    for epoch in range(epochs):
        model.train()
        for xb, yb in loader:
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

        model.eval()
        with torch.no_grad():
            val_loss = criterion(model(X_vl), y_vl).item()
        scheduler.step(val_loss)

        if val_loss < best_val - 1e-6:
            best_val, no_improve = val_loss, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            no_improve += 1
            if no_improve >= patience:
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    return {"best_epoch": epoch - no_improve, "best_val_loss": best_val}


def evaluate_model_cols(model, test_df, feature_cols, threshold=0.5, device="cpu") -> Dict:
    """evaluate_model but reading an arbitrary feature-column list."""
    model = model.to(device).eval()
    X, y = _prep(test_df, feature_cols)
    X, y = X.to(device), y.to(device)
    with torch.no_grad():
        probs = torch.sigmoid(model(X).squeeze(1)).cpu().numpy()
        labels = y.squeeze(1).cpu().numpy()
    preds = (probs >= threshold).astype(float)
    tp = float(((preds == 1) & (labels == 1)).sum())
    fp = float(((preds == 1) & (labels == 0)).sum())
    fn = float(((preds == 0) & (labels == 1)).sum())
    tn = float(((preds == 0) & (labels == 0)).sum())
    n_trades = tp + fp
    return {
        "accuracy": round((tp + tn) / max(len(labels), 1), 4),
        "win_rate": round(tp / max(n_trades, 1), 4),
        "recall": round(tp / max(tp + fn, 1), 4),
        "profit_factor": round((tp * 2.0) / max(fp * 1.0, 1e-8), 3),
        "n_trades": int(n_trades),
        "n_total": len(labels),
    }


def compare_architectures_cols(
    dataset: pd.DataFrame,
    feature_cols: List[str] = FEATURE_NAMES_V2,
    epochs: int = 150,
    patience: int = 20,
    verbose: bool = True,
    device: str = "cpu",
) -> Tuple[pd.DataFrame, nn.Module]:
    """Train all three architectures on ``feature_cols``.

    Returns (results_table, trained_perceptron) so the caller can read weights.
    """
    if len(dataset) < 30:
        raise ValueError(f"Only {len(dataset)} setups — need >= 30 to train.")

    ds = dataset.sort_values("entry_time").reset_index(drop=True)
    train_df, val_df, test_df = walk_forward_split(ds)
    n_feat = len(feature_cols)

    if verbose:
        print(f"\n[brain-v2] {len(ds)} setups | {n_feat} features")
        print(f"  Train {len(train_df)}  Val {len(val_df)}  Test {len(test_df)}")
        print(f"  Baseline FVG-tap win rate: {100 * ds['label'].mean():.1f}%\n")

    results, perceptron = [], None
    for arch in ARCHITECTURES:
        model = get_model(arch, n_features=n_feat)
        n_params = sum(p.numel() for p in model.parameters())
        train_model_cols(model, train_df, val_df, feature_cols,
                         epochs=epochs, patience=patience, device=device)
        metrics = evaluate_model_cols(model, test_df, feature_cols, device=device)
        metrics["architecture"] = arch
        metrics["n_params"] = n_params
        results.append(metrics)
        if arch == "perceptron":
            perceptron = model
        if verbose:
            print(f"  {arch:11s} | WR={metrics['win_rate']:.1%} | "
                  f"PF={metrics['profit_factor']:.2f} | "
                  f"trades={metrics['n_trades']}/{metrics['n_total']} | params={n_params}")

    return pd.DataFrame(results).set_index("architecture"), perceptron


def perceptron_weights(model: nn.Module, feature_cols: List[str]) -> Dict[str, float]:
    """Read {feature: weight} from a v2 Perceptron over ``feature_cols``."""
    w = model.linear.weight.detach().cpu().squeeze().numpy()
    return dict(zip(feature_cols, w.tolist()))

"""Walk-forward training and evaluation for the MMC decision brain.

Walk-forward is mandatory for trading models — random k-fold would let the
model peek at the future (a bar from Dec 2023 in the training fold, while
Jan 2023 is in the test fold).

Split strategy:
    Train   : first 70% of data (chronological)
    Validate: next 15%          (used for early stopping)
    Test    : final 15%         (untouched until evaluation)

An embargo gap of ``embargo_bars`` rows between train/val/test prevents
information leakage from overlapping look-back windows.

Usage:
    from mmc.brain.train import compare_architectures
    results = compare_architectures(dataset)   # DataFrame with per-arch metrics
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from mmc.brain.architectures import ARCHITECTURES, get_model
from mmc.brain.features import FEATURE_NAMES, N_FEATURES


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _prepare_tensors(
    df: pd.DataFrame,
    feature_cols: List[str] = FEATURE_NAMES,
) -> Tuple[torch.Tensor, torch.Tensor]:
    X = torch.tensor(df[feature_cols].values, dtype=torch.float32)
    y = torch.tensor(df["label"].values, dtype=torch.float32).unsqueeze(1)
    return X, y


def walk_forward_split(
    df: pd.DataFrame,
    train_frac: float = 0.70,
    val_frac:   float = 0.15,
    embargo:    int   = 10,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split dataset chronologically into train / val / test sets.

    ``embargo`` rows are dropped between each split to prevent information
    leakage from features computed over a look-back window.
    """
    n = len(df)
    i_val  = int(n * train_frac)
    i_test = int(n * (train_frac + val_frac))

    train = df.iloc[:max(0, i_val - embargo)]
    val   = df.iloc[i_val:max(i_val, i_test - embargo)]
    test  = df.iloc[i_test:]

    return train.reset_index(drop=True), val.reset_index(drop=True), test.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

def train_model(
    model: nn.Module,
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    epochs: int = 150,
    lr: float = 1e-3,
    batch_size: int = 64,
    patience: int = 20,
    device: str = "cpu",
) -> Dict:
    """Train ``model`` with early stopping on validation loss.

    Returns a history dict with train_loss, val_loss per epoch and the
    best epoch.
    """
    model = model.to(device)
    X_tr, y_tr = _prepare_tensors(train_df)
    X_vl, y_vl = _prepare_tensors(val_df)
    X_tr, y_tr = X_tr.to(device), y_tr.to(device)
    X_vl, y_vl = X_vl.to(device), y_vl.to(device)

    # Class imbalance: weight the loss by inverse class frequency
    n_pos = float(y_tr.sum())
    n_neg = float(len(y_tr) - n_pos)
    pos_weight = torch.tensor([n_neg / max(n_pos, 1)], device=device)

    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, patience=10, factor=0.5, min_lr=1e-5
    )

    loader = DataLoader(TensorDataset(X_tr, y_tr), batch_size=batch_size, shuffle=True)

    best_val_loss = float("inf")
    best_state    = None
    no_improve    = 0
    history       = {"train_loss": [], "val_loss": []}

    model.train()
    for epoch in range(epochs):
        epoch_loss = 0.0
        model.train()
        for xb, yb in loader:
            optimizer.zero_grad()
            logits = model(xb)
            loss   = criterion(logits, yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            epoch_loss += loss.item() * len(xb)
        epoch_loss /= len(X_tr)

        model.eval()
        with torch.no_grad():
            val_loss = criterion(model(X_vl), y_vl).item()

        scheduler.step(val_loss)
        history["train_loss"].append(epoch_loss)
        history["val_loss"].append(val_loss)

        if val_loss < best_val_loss - 1e-6:
            best_val_loss = val_loss
            best_state    = {k: v.clone() for k, v in model.state_dict().items()}
            no_improve    = 0
        else:
            no_improve += 1
            if no_improve >= patience:
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    history["best_epoch"]   = epoch - no_improve
    history["best_val_loss"] = best_val_loss
    return history


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_model(
    model: nn.Module,
    test_df: pd.DataFrame,
    threshold: float = 0.5,
    device: str = "cpu",
) -> Dict:
    """Evaluate a trained model on the held-out test set.

    Returns:
        accuracy    — fraction of correct binary predictions
        precision   — TP / (TP + FP)
        recall      — TP / (TP + FN)
        win_rate    — fraction of *predicted positive* that won (= precision)
        profit_factor — total R won / total R lost (simulated at fixed 2R TP)
        n_trades    — number of setups the model approved (predicted positive)
        n_total     — total test setups
    """
    model = model.to(device)
    model.eval()
    X, y = _prepare_tensors(test_df)
    X, y = X.to(device), y.to(device)

    with torch.no_grad():
        logits = model(X).squeeze(1)
        probs  = torch.sigmoid(logits).cpu().numpy()
        labels = y.squeeze(1).cpu().numpy()

    preds = (probs >= threshold).astype(float)

    tp = float(((preds == 1) & (labels == 1)).sum())
    fp = float(((preds == 1) & (labels == 0)).sum())
    fn = float(((preds == 0) & (labels == 1)).sum())
    tn = float(((preds == 0) & (labels == 0)).sum())

    n_trades = tp + fp
    accuracy  = (tp + tn) / max(len(labels), 1)
    precision = tp / max(n_trades, 1)
    recall    = tp / max(tp + fn, 1)

    # Profit factor: approved trades only, TP=2R SL=1R
    r_per_win  = 2.0
    r_per_loss = 1.0
    total_r_won  = tp * r_per_win
    total_r_lost = fp * r_per_loss
    pf = total_r_won / max(total_r_lost, 1e-8)

    return {
        "accuracy":      round(accuracy,  4),
        "win_rate":      round(precision, 4),
        "recall":        round(recall,    4),
        "profit_factor": round(pf,        3),
        "n_trades":      int(n_trades),
        "n_total":       len(labels),
        "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
    }


# ---------------------------------------------------------------------------
# Compare all three architectures on the same data split
# ---------------------------------------------------------------------------

def compare_architectures(
    dataset: pd.DataFrame,
    epochs: int = 150,
    patience: int = 20,
    verbose: bool = True,
    device: str = "cpu",
) -> pd.DataFrame:
    """Train all three architectures on the same walk-forward split and return
    a comparison table.

    This is the core experiment: if ShallowNN beats Perceptron out-of-sample,
    the concept combinations are worth modelling; if DeepNN beats ShallowNN,
    there's enough data to support depth.
    """
    if len(dataset) < 30:
        raise ValueError(
            f"Only {len(dataset)} setups found — need at least 30 to train. "
            "Run more data or lower MIN_RR in dataset.py."
        )

    # Sort chronologically and split
    ds = dataset.sort_values("entry_time").reset_index(drop=True)
    train_df, val_df, test_df = walk_forward_split(ds)

    if verbose:
        print(f"\n[brain] Dataset: {len(ds)} setups total")
        print(f"  Train: {len(train_df)}  Val: {len(val_df)}  Test: {len(test_df)}")
        win_pct = 100 * ds["label"].mean()
        print(f"  Overall win rate (rule engine): {win_pct:.1f}%\n")

    results = []
    for arch_name in ARCHITECTURES:
        if verbose:
            print(f"[brain] Training {arch_name}...")

        model = get_model(arch_name)
        n_params = sum(p.numel() for p in model.parameters())

        history = train_model(
            model, train_df, val_df,
            epochs=epochs, patience=patience, device=device
        )
        metrics = evaluate_model(model, test_df, device=device)
        metrics["architecture"] = arch_name
        metrics["n_params"]     = n_params
        metrics["best_epoch"]   = history["best_epoch"]
        results.append(metrics)

        if verbose:
            print(
                f"  {arch_name:12s} | "
                f"WR={metrics['win_rate']:.1%} | "
                f"PF={metrics['profit_factor']:.2f} | "
                f"trades={metrics['n_trades']}/{metrics['n_total']} | "
                f"params={n_params}"
            )

    return pd.DataFrame(results).set_index("architecture")


# ---------------------------------------------------------------------------
# Feature importance (perceptron only — readable weights)
# ---------------------------------------------------------------------------

def print_feature_importance(model: nn.Module, top_n: int = 15) -> None:
    """Print the top-N most influential features for a Perceptron model."""
    if not hasattr(model, "feature_weights"):
        print("Feature importance is only directly readable from the Perceptron.")
        return
    weights = model.feature_weights()
    ranked = sorted(weights.items(), key=lambda kv: abs(kv[1]), reverse=True)
    print(f"\n{'Feature':<25} {'Weight':>10}")
    print("-" * 38)
    for name, w in ranked[:top_n]:
        bar = "#" * int(abs(w) * 20)
        sign = "+" if w > 0 else "-"
        print(f"{name:<25} {sign}{abs(w):>8.4f}  {bar}")

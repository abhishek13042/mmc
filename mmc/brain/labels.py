"""Trade outcome labelling for the MMC brain.

For each detected entry signal we simulate the trade forward in the
entry-timeframe data:

    - Win  (1.0): take-profit price hit before stop-loss
    - Loss (0.0): stop-loss hit first
    - None:       neither hit within ``max_bars`` — excluded from training

Stop-loss and take-profit levels come from the engine's Entry objects so the
label reflects *exactly* what the rule-based system would have executed.

Key insight from ANALYSIS.md: min_rr=2.0 is the sweet spot. The dataset
generator filters setups whose TP is less than 2R away.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def label_trade(
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    df: pd.DataFrame,
    entry_bar: int,
    max_bars: int = 200,
) -> Optional[float]:
    """Simulate a trade from ``entry_bar`` and return 1.0 (win), 0.0 (loss),
    or None (timeout).

    Uses bar high/low so we catch wicks that touch SL or TP intra-bar.
    When both are touched on the same bar we assume the worse outcome (SL hit)
    — conservative labelling avoids inflating win rate.

    Args:
        entry_price:  The fill price (e.g. FVG edge).
        stop_loss:    Stop-loss price.
        take_profit:  Take-profit price.
        df:           Entry-timeframe OHLCV DataFrame.
        entry_bar:    Integer bar position where the trade is entered.
        max_bars:     Maximum bars to simulate forward before timeout.
    """
    if abs(stop_loss - entry_price) < 1e-10:
        return None

    is_long = take_profit > entry_price
    highs = df["high"].to_numpy()
    lows  = df["low"].to_numpy()
    n = len(df)

    for j in range(entry_bar + 1, min(n, entry_bar + max_bars + 1)):
        sl_hit = lows[j] <= stop_loss if is_long else highs[j] >= stop_loss
        tp_hit = highs[j] >= take_profit if is_long else lows[j] <= take_profit

        if sl_hit and tp_hit:
            return 0.0  # conservative: assume SL hit first
        if tp_hit:
            return 1.0
        if sl_hit:
            return 0.0

    return None  # timeout — exclude from training


def label_trade_rr(
    entry_price: float,
    stop_loss: float,
    df: pd.DataFrame,
    entry_bar: int,
    target_rr: float = 2.0,
    max_bars: int = 200,
) -> Optional[float]:
    """Same as :func:`label_trade` but derives TP from a fixed RR ratio.

    Useful when testing whether the model can predict trade quality without
    needing the engine's ITH/ITL detection.
    """
    risk = abs(entry_price - stop_loss)
    if risk < 1e-10:
        return None
    direction = 1 if stop_loss < entry_price else -1
    take_profit = entry_price + direction * risk * target_rr
    return label_trade(entry_price, stop_loss, take_profit, df, entry_bar, max_bars)


def compute_r_multiple(
    entry_price: float,
    stop_loss: float,
    exit_price: float,
) -> float:
    """Convert an exit price to an R multiple (+ = profit, - = loss)."""
    risk = abs(entry_price - stop_loss)
    if risk < 1e-10:
        return 0.0
    direction = 1 if stop_loss < entry_price else -1
    return direction * (exit_price - entry_price) / risk

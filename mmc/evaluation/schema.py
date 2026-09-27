"""Canonical per-trade log schema + loader.

The whole pipeline is source-agnostic: anything that can emit this CSV (the
live-MT5 exporter in ``examples/mt5_oos_test.py`` today, an offline backtest
tomorrow) can be evaluated. One row == one *filled* trade, and every money-like
quantity is an R-multiple so the numbers mean the same thing on EURUSD and
XAUUSD (same convention as :mod:`mmc.backtest.result`).
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd

# --------------------------------------------------------------------------- #
# Canonical columns
# --------------------------------------------------------------------------- #

# Columns every trade log MUST contain to be evaluable.
REQUIRED_COLUMNS: List[str] = [
    "strategy_id",   # "{pair}_{combo}_rr{rr}" — the fleet strategy name
    "entry_time",    # timestamp the position opened
    "r_multiple",    # net realised R (after spread_cost); +rr win, -1 loss
]

# Full set the exporter writes; optional ones enrich the analysis when present.
TRADE_COLUMNS: List[str] = [
    "strategy_id", "pair", "combo", "rr",
    "entry_time", "exit_time", "direction",
    "entry_price", "stop", "take_profit", "risk",
    "score", "outcome",
    "r_multiple", "spread_cost", "bars_held",
    "split", "source", "run_ts",
]

_FLOAT_COLS = ["rr", "entry_price", "stop", "take_profit", "risk",
               "score", "r_multiple", "spread_cost"]
_INT_COLS = ["bars_held"]
_TIME_COLS = ["entry_time", "exit_time"]


class SchemaError(ValueError):
    """Raised when a trade log is missing required columns."""


def load_trades(path: str) -> pd.DataFrame:
    """Load and validate a trade-log CSV into a normalised DataFrame.

    * verifies the required columns exist,
    * coerces dtypes (floats, ints, timestamps),
    * sorts by ``entry_time`` within each strategy,
    * back-fills a ``win`` boolean and a ``pair``/``combo``/``rr`` parse from
      ``strategy_id`` when those optional columns are absent.

    Raises :class:`SchemaError` on a missing required column.
    """
    df = pd.read_csv(path)
    return normalise_trades(df)


def normalise_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce/validate an already-loaded trade DataFrame (shared by the loader
    and by the unit tests that build frames in memory)."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise SchemaError(
            f"trade log missing required column(s): {missing}. "
            f"Present: {list(df.columns)}"
        )

    df = df.copy()

    for c in _TIME_COLS:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")

    for c in _FLOAT_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    for c in _INT_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")

    # Derive a plain win flag from either `outcome` or the R sign.
    if "outcome" in df.columns:
        df["win"] = df["outcome"].astype(str).str.lower().eq("win")
    else:
        df["win"] = df["r_multiple"] > 0

    # Parse pair / combo / rr out of strategy_id when not provided.
    if not {"pair", "combo", "rr"}.issubset(df.columns):
        parsed = df["strategy_id"].apply(_parse_strategy_id)
        for k in ("pair", "combo", "rr"):
            if k not in df.columns:
                df[k] = parsed.apply(lambda d: d.get(k))

    df = df.sort_values(["strategy_id", "entry_time"]).reset_index(drop=True)
    return df


def _parse_strategy_id(sid: str) -> Dict[str, object]:
    """"EURUSD_H4_H1_rr4" -> {pair, combo, rr}. Best-effort; unknown -> {}."""
    try:
        parts = str(sid).split("_")
        # last token like "rr4" (or "3R"); pair is first; combo is the middle.
        rr_tok = parts[-1].lower().replace("rr", "").replace("r", "")
        rr = float(rr_tok)
        pair = parts[0]
        combo = "_".join(parts[1:-1])
        return {"pair": pair, "combo": combo, "rr": rr}
    except Exception:
        return {}


def split_by_strategy(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Group a normalised trade log into ``{strategy_id: trades}``, each sorted
    by entry_time."""
    return {
        sid: g.sort_values("entry_time").reset_index(drop=True)
        for sid, g in df.groupby("strategy_id", sort=True)
    }

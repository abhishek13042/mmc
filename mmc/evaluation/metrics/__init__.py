"""Metric families. Each module takes an R-multiple series (a strategy's
``r_multiple`` column, in trade order) and returns plain floats / dataclasses —
no plotting, no I/O — so they compose and unit-test cleanly."""

from mmc.evaluation.metrics import (
    core,
    statval,
    drawdown,
    riskadj,
    stability,
    robustness,
    portfolio,
)

__all__ = [
    "core", "statval", "drawdown", "riskadj",
    "stability", "robustness", "portfolio",
]

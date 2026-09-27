"""Statistical-validity layer — the gate before any other number means anything.

A point-estimate WR/PF on 30 trades is noise. This module quantifies the noise:

  * Wilson score interval on win rate (better small-N behaviour than Wald),
  * bootstrap confidence bands on PF and expectancy (resample trades with
    replacement -> distribution of the metric, report the tails),
  * standard error of expectancy.

Everything is numpy-only so scipy stays a soft dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

# z for a two-sided 95% interval; good enough without scipy. We interpolate a
# couple of common levels and fall back to 1.96.
_Z = {0.90: 1.6448536269514722, 0.95: 1.959963984540054, 0.99: 2.5758293035489004}


def _z_for(conf: float) -> float:
    return _Z.get(round(conf, 2), 1.959963984540054)


def wilson_interval(wins: int, n: int, conf: float = 0.95) -> Tuple[float, float]:
    """Wilson score confidence interval for a binomial proportion (win rate).

    Returns ``(low, high)`` in [0, 1]. Degenerate ``n == 0`` -> ``(0, 0)``.
    """
    if n <= 0:
        return (0.0, 0.0)
    z = _z_for(conf)
    p = wins / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (z * np.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


@dataclass
class BootstrapBand:
    metric: str
    point: float
    low: float          # lower percentile (e.g. 2.5th)
    high: float         # upper percentile (e.g. 97.5th)
    p5: float           # 5th percentile — the "pessimistic" read used for gating


def _profit_factor(r: np.ndarray) -> float:
    gp = r[r > 0].sum()
    gl = -r[r < 0].sum()
    if gl <= 0:
        return float("inf") if gp > 0 else 0.0
    return gp / gl


def bootstrap_bands(
    r: np.ndarray,
    iters: int = 1000,
    conf: float = 0.95,
    seed: int = 12345,
) -> Tuple[BootstrapBand, BootstrapBand]:
    """Bootstrap confidence bands for (profit_factor, expectancy).

    Resamples the trade R-array with replacement ``iters`` times. Returns a
    ``BootstrapBand`` for PF and for ExpR. ``p5`` (5th percentile) is exposed
    separately because the qualification gate uses the pessimistic tail of PF,
    not the point estimate.
    """
    r = np.asarray(r, dtype=float)
    n = r.size
    lo_pct = 100.0 * (1.0 - conf) / 2.0
    hi_pct = 100.0 - lo_pct

    if n == 0:
        z = BootstrapBand("", 0.0, 0.0, 0.0, 0.0)
        return (BootstrapBand("profit_factor", 0, 0, 0, 0),
                BootstrapBand("expectancy", 0, 0, 0, 0))

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(iters, n))
    samples = r[idx]                                   # (iters, n)

    exp_dist = samples.mean(axis=1)
    # vectorised PF per resample
    pos = np.where(samples > 0, samples, 0.0).sum(axis=1)
    neg = np.where(samples < 0, -samples, 0.0).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        pf_dist = np.where(neg > 0, pos / neg, np.inf)
    pf_finite = pf_dist[np.isfinite(pf_dist)]

    def _band(name, dist, point):
        if dist.size == 0:
            return BootstrapBand(name, point, point, point, point)
        return BootstrapBand(
            metric=name,
            point=float(point),
            low=float(np.percentile(dist, lo_pct)),
            high=float(np.percentile(dist, hi_pct)),
            p5=float(np.percentile(dist, 5.0)),
        )

    pf_point = _profit_factor(r)
    pf_band = _band("profit_factor", pf_finite, pf_point)
    exp_band = _band("expectancy", exp_dist, r.mean())
    return pf_band, exp_band


def expectancy_stderr(r: np.ndarray) -> float:
    """Standard error of mean R (expectancy). ``0`` for n < 2."""
    r = np.asarray(r, dtype=float)
    n = r.size
    if n < 2:
        return 0.0
    return float(r.std(ddof=1) / np.sqrt(n))

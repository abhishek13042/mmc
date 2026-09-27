"""Pre-committed qualification thresholds.

The point of committing these *before* looking at the output is that you can't
unconsciously bend the bar to let a favourite strategy through — which defeats
the entire purpose of evaluating rigorously. Defaults are the user's spec; every
field is overridable at the CLI / call site.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualifyConfig:
    """Thresholds + knobs for qualification and the derived analyses.

    Gating thresholds (a strategy must clear ALL to PASS):
      * ``min_n``            — below this, tier = "insufficient data" and the
                               other gates are reported but not decisive.
      * ``min_bootstrap_pf`` — the 5th-percentile bootstrap PF (not the point
                               estimate) must exceed this.
      * ``min_recovery``     — recovery factor (total R / max DD) floor.
      * ``max_is_oos_decay`` — max allowed fractional PF drop from in-sample
                               (RESULTS_TABLE) to out-of-sample (this log).

    Analysis knobs:
      * ``bootstrap_iters`` / ``mc_iters`` — resample counts.
      * ``rng_seed``        — fixed so reports are reproducible.
      * ``bars_per_year``   — annualisation factor for Calmar. Left as trading
                               days by default; only affects Calmar's scale.
      * ``spread_stress``   — multiplier applied to spread_cost for the
                               execution-reality sensitivity column.
      * ``commission_r``    — extra per-trade cost in R (commission/swap drag)
                               applied in the sensitivity column.
    """

    # --- gating thresholds ---
    min_n: int = 100
    min_bootstrap_pf: float = 1.2
    min_recovery: float = 2.0
    max_is_oos_decay: float = 0.30

    # --- analysis knobs ---
    bootstrap_iters: int = 1000
    mc_iters: int = 1000
    rng_seed: int = 12345
    conf_level: float = 0.95            # Wilson CI + bootstrap band coverage
    trades_per_year: float = 252.0      # Calmar annualisation (assume ~daily)

    # --- execution-reality sensitivity ---
    spread_stress: float = 1.5          # re-price PF/ExpR at 1.5x spread
    commission_r: float = 0.0           # extra R drag per trade (broker-specific)

    @property
    def bootstrap_low_pct(self) -> float:
        return 100.0 * (1.0 - self.conf_level) / 2.0

    @property
    def bootstrap_high_pct(self) -> float:
        return 100.0 * (1.0 - (1.0 - self.conf_level) / 2.0)

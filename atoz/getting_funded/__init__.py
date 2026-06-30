"""atoz.getting_funded — risk, funding rules and readiness checklist.

Faithful implementation of two mostly-mindset A-Z Guide episodes:
    ep 38 — "Things You NEED to know before You Start Trading" (file 039)
    ep 39 — "Guide to Get Funded / Make Money"                 (file 040)

These episodes are largely psychology/business. What is CODIFIABLE was extracted
into three modules; everything else is preserved as quoted narrative inside the
module docstrings and the checklist quotes.

CODIFIED:
  risk.py      — position sizing (account * risk% / stop), a drawdown risk
                 ladder (1% -> 0.5% -> 0.25%, ep 39), R-multiple and 1:2-RR
                 expectancy math.
  funding.py   — PropFirmCriteria dataclass + walk an equity curve / trade list
                 for pass / breach (daily-loss, total-drawdown, profit-target,
                 min-days, consistency rule), and the 2% payout target.
  checklist.py — the instructor's enumerated "things you need to know" / "steps
                 to get funded" as an ordered, quoted, partly-gating checklist.

NARRATIVE-ONLY (not codified — no arithmetic): don't backtest, follow one mentor,
stay off social media, don't idolize, "submit to time", "enjoy the process",
"take responsibility", "don't use the prop firm as an excuse". These are quoted
in the module docstrings / checklist but have no pass-fail function.
"""

from .checklist import (
    CHECKLIST,
    Episode,
    ReadinessItem,
    ReadinessState,
    gating_items,
    print_checklist,
    ready_to_trade,
)
from .funding import (
    BreachKind,
    EvalOutcome,
    EvalResult,
    PropFirmCriteria,
    check_consistency,
    equity_curve_from_trades,
    evaluate_daily_equity,
    payout_target_hit,
)
from .risk import (
    PositionSize,
    RiskLadder,
    RiskStep,
    expectancy,
    position_size,
    r_multiple,
)

__all__ = [
    # risk
    "PositionSize", "position_size",
    "RiskLadder", "RiskStep",
    "r_multiple", "expectancy",
    # funding
    "PropFirmCriteria", "EvalOutcome", "EvalResult", "BreachKind",
    "evaluate_daily_equity", "equity_curve_from_trades",
    "check_consistency", "payout_target_hit",
    # checklist
    "CHECKLIST", "Episode", "ReadinessItem", "ReadinessState",
    "gating_items", "ready_to_trade", "print_checklist",
]

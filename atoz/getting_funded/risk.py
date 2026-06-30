"""Risk management — A-Z Guide ep 39 ("Guide to Get Funded / Make Money", file 040).

This module codifies the *risk-management* rules the instructor calls the single
biggest secret to getting funded. Everything here is a pure function or an
immutable dataclass; there is no price logic and therefore no look-ahead concern.

Quoted rules from ep 39 (file 040):

* "risk management is extremely important ... if you have the right risk
  management approach then there is no reason to fail literally zero."
* "people when they go into drawdown they get scared and they up their risk
  eventually instead of lowering their risk. You always want to lower your
  risk. So you want to have risk parameters. You want to know when am I dropping
  my risk to 0.5%? When am I dropping my risk even to 0.25%?"
* "Just aim for a 1 to 2 RR with around even a 50%, 40% win rate ... 50% win
  rate, 1 to 2 RR, you can't fail."
* "you don't need to get a payout of 10%, 15%. No, a 2% payout is fine ... Just
  get that payout and that refund from the fee that you paid for that challenge."
* "treat it like a business ... start with a small funded account, whatever you
  can afford ... make the business generate cashflow itself ... from the 2%
  payout and the refund you buy another one and then you repeat the process."

NARRATIVE-ONLY (not codified — mindset, no numeric rule):
  - "risk management goes hand in hand with your psychology" (ep 39)
  - "fail, fail, fail, win" / "submit to time" / "enjoy the process" (ep 38/39)
  - the whole of ep 38 (file 039) is mindset: don't backtest, follow one mentor,
    no shiny-object syndrome, don't idolize, jump in the deep end. See
    ``checklist.py`` for the codifiable structured form of those lessons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# --------------------------------------------------------------------------- #
# Position sizing
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PositionSize:
    """Result of a position-sizing calculation.

    ``risk_amount`` is the cash put at risk; ``units`` is the raw position size
    (in price-units of the instrument, e.g. lots * contract size left to the
    caller) such that ``units * stop_distance == risk_amount``.
    """

    account_size: float
    risk_pct: float
    stop_distance: float
    risk_amount: float
    units: float


def position_size(
    account_size: float,
    risk_pct: float,
    stop_distance: float,
) -> PositionSize:
    """Size a position from account, risk-% and stop distance (ep 39).

    The instructor's whole risk doctrine is "know what % you are risking and be
    able to lower it" (he names 1%, 0.5%, 0.25% explicitly). Position size is the
    fixed-fractional formula:

        risk_amount = account_size * risk_pct / 100
        units       = risk_amount / stop_distance

    ``stop_distance`` is the price distance from entry to stop (same units as
    price). ``risk_pct`` is a whole-number percent (1.0 == 1%), matching how the
    instructor speaks ("dropping my risk to 0.5%").

    Raises ``ValueError`` on non-positive account, negative risk, or
    non-positive stop distance (you cannot size against a zero stop).
    """
    if account_size <= 0:
        raise ValueError("account_size must be positive")
    if risk_pct < 0:
        raise ValueError("risk_pct must be >= 0")
    if stop_distance <= 0:
        raise ValueError("stop_distance must be positive")

    risk_amount = account_size * risk_pct / 100.0
    units = risk_amount / stop_distance
    return PositionSize(
        account_size=account_size,
        risk_pct=risk_pct,
        stop_distance=stop_distance,
        risk_amount=risk_amount,
        units=units,
    )


# --------------------------------------------------------------------------- #
# Drawdown-ladder risk parameters
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RiskStep:
    """One rung of the drawdown ladder: at/under ``drawdown_pct`` of peak equity,
    risk drops to ``risk_pct`` per trade."""

    drawdown_pct: float   # current drawdown from peak, in percent (>= 0)
    risk_pct: float       # per-trade risk to use at/under this drawdown


@dataclass(frozen=True)
class RiskLadder:
    """The instructor's "risk parameters": as drawdown deepens, lower risk.

    > "You want to know when am I dropping my risk to 0.5%? When am I dropping my
    > risk even to 0.25%? ... You always want to lower your risk."  — ep 39

    Steps are kept sorted by ascending ``drawdown_pct``. ``base_risk_pct`` is the
    risk used while equity is at/above its peak (zero drawdown).
    """

    base_risk_pct: float = 1.0
    steps: List[RiskStep] = field(default_factory=list)

    @classmethod
    def instructor_default(cls) -> "RiskLadder":
        """The exact ladder the instructor verbalises: 1% normally, 0.5% in
        drawdown, 0.25% in deeper drawdown (ep 39). The drawdown thresholds for
        each rung are NOT given a number in the transcript, so we pick sensible,
        clearly-marked break-points (5% and 8%); the *risk values* are his."""
        return cls(
            base_risk_pct=1.0,
            steps=[
                RiskStep(drawdown_pct=5.0, risk_pct=0.5),
                RiskStep(drawdown_pct=8.0, risk_pct=0.25),
            ],
        )

    def risk_for_drawdown(self, drawdown_pct: float) -> float:
        """Return the per-trade risk-% to use at the given current drawdown.

        Picks the deepest rung whose threshold is <= the current drawdown; if no
        rung applies (shallow / no drawdown) returns ``base_risk_pct``. "You
        always want to lower your risk" — risk is monotonically non-increasing
        as drawdown grows."""
        risk = self.base_risk_pct
        for step in sorted(self.steps, key=lambda s: s.drawdown_pct):
            if drawdown_pct >= step.drawdown_pct:
                risk = step.risk_pct
        return risk


# --------------------------------------------------------------------------- #
# R-multiple math
# --------------------------------------------------------------------------- #


def r_multiple(entry: float, stop: float, exit_price: float = None, exit: float = None) -> float:
    """R-multiple of a closed trade: profit measured in units of initial risk.

    1R == the entry-to-stop distance. A trade that hits a 1:2 target returns
    +2R; a trade stopped out returns -1R. The instructor frames everything as
    RR: "Just aim for a 1 to 2 RR" (ep 39).

    Direction is inferred from stop placement: stop below entry => long, stop
    above entry => short. Raises ``ValueError`` if entry == stop (zero risk).

    The exit price can be supplied as either ``exit_price`` or ``exit``
    (the latter being the short keyword used in the test harness).
    """
    # Resolve exit price from either kwarg name.
    if exit_price is None and exit is None:
        raise ValueError("must provide exit_price (or exit=) for the closing price")
    if exit_price is None:
        exit_price = exit
    risk = abs(entry - stop)
    if risk == 0:
        raise ValueError("entry and stop cannot be equal (zero risk)")
    if stop < entry:        # long: stop below entry
        return (exit_price - entry) / risk
    return (entry - exit_price) / risk   # short: stop above entry


def expectancy(
    win_rate: float,
    reward_risk: float = None,
    avg_win_r: float = None,
    avg_loss_r: float = 1.0,
) -> float:
    """Expected R per trade for a given win rate and reward:risk (ep 39).

    > "50% win rate, 1 to 2 RR, you can't fail."

    Two calling conventions:

    1. ``expectancy(win_rate, reward_risk)`` — the classic form. Loss leg is
       assumed to be 1R (the instructor always quotes 1:2 ratios as the win leg
       only).  ``E[R] = p * rr - (1 - p) * 1``

    2. ``expectancy(win_rate, avg_win_r=2.0, avg_loss_r=1.0)`` — explicit
       separate legs. ``E[R] = p * avg_win_r - (1 - p) * avg_loss_r``

    ``win_rate`` is a fraction in [0, 1].  Default ``avg_loss_r = 1.0`` (1R
    loss) matches the instructor's "aim for 1 to 2 RR" phrasing.
    """
    if not 0.0 <= win_rate <= 1.0:
        raise ValueError("win_rate must be in [0, 1]")

    if reward_risk is not None:
        # Classic form: loss leg is 1R.
        if reward_risk <= 0:
            raise ValueError("reward_risk must be positive")
        return win_rate * reward_risk - (1.0 - win_rate)

    # Explicit avg_win_r / avg_loss_r form.
    if avg_win_r is None:
        raise ValueError("must provide reward_risk or avg_win_r")
    if avg_win_r <= 0:
        raise ValueError("avg_win_r must be positive")
    if avg_loss_r <= 0:
        raise ValueError("avg_loss_r must be positive")
    return win_rate * avg_win_r - (1.0 - win_rate) * avg_loss_r

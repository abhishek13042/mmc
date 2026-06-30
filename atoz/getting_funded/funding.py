"""Prop-firm / funding-rules checker — A-Z Guide ep 39 (file 040).

The instructor's third step is choosing a firm and passing its evaluation. He
does not invent the prop-firm rule *names* (profit target / daily loss / total
drawdown / minimum days are the standard evaluation parameters every funded
trader must respect); what the transcript codifies is *how to behave* against
them: lower risk in drawdown, take a small 2% payout, don't blow the account
chasing 10%.

This module gives a dataclass for an evaluation's hard rules and pure functions
to walk a running equity curve / trade list and decide pass vs. breach.

Quoted, codified rules from ep 39 (file 040):

* "look for preferably a prop firm with one to 100 [leverage]" — captured as an
  advisory field ``leverage`` on :class:`PropFirmCriteria` (narrative advice,
  surfaced as data, not enforced here).
* "look for a prop firm with no consistency rule. A consistency rule is
  basically you need to use the same amount of lot sizes over and over and over.
  If that doesn't happen, then they can remove you from the account." — codified
  as :func:`check_consistency`.
* "a 2% payout is fine ... Just get that payout and that refund from the fee" —
  codified as :func:`payout_target_hit`.
* drawdown discipline ("when you go into drawdown ... lower your risk") lives in
  ``risk.RiskLadder``; here we only *detect* the breach.

NARRATIVE-ONLY (ep 39, not codified): "don't use the prop firm as an excuse",
"choose a well-known prop firm", "search the discord for slippage/spreads",
"take responsibility for your losses and your wins". These are choice/mindset
guidance with no pass/fail arithmetic — see ``checklist.py``.

No look-ahead: every check consumes the equity curve left-to-right and reports
the first breaching bar; nothing peeks at future equity to decide a past bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence


class EvalOutcome(Enum):
    """Result of evaluating an account against a firm's rules."""

    PASSED = "passed"           # profit target reached, no rule breached
    BREACHED = "breached"       # a hard rule was violated -> account lost
    IN_PROGRESS = "in_progress" # neither passed nor breached yet


class BreachKind(Enum):
    MAX_DAILY_LOSS = "max_daily_loss"
    MAX_TOTAL_DRAWDOWN = "max_total_drawdown"
    CONSISTENCY = "consistency"


@dataclass(frozen=True)
class PropFirmCriteria:
    """The hard rules of a prop-firm evaluation / funded account.

    All loss/target/drawdown figures are *percent of the starting balance*
    (whole-number percent: 10.0 == 10%), matching how challenges are advertised
    and how the instructor speaks ("a 2% payout").

    Fields:
      profit_target_pct   — equity gain (% of start) required to pass.
      max_daily_loss_pct  — max loss within a single trading day (% of start).
      max_total_drawdown_pct — max equity drop from the start balance (% of
                            start). (Some firms measure trailing from peak; this
                            implementation uses the common static start-balance
                            rule and documents it.)
      min_trading_days    — minimum number of distinct trading days required.
      leverage            — advisory only ("preferably one to 100"); not enforced.
      no_consistency_rule — advisory: True means the chosen firm has NO
                            consistency rule, which is what the instructor tells
                            you to "look for". When False, callers may run
                            :func:`check_consistency`.
    """

    profit_target_pct: float
    max_daily_loss_pct: float
    max_total_drawdown_pct: float
    min_trading_days: int = 0
    leverage: int = 100
    no_consistency_rule: bool = True


@dataclass(frozen=True)
class EvalResult:
    outcome: EvalOutcome
    breach: Optional[BreachKind] = None
    breach_day: Optional[int] = None     # index into the daily series
    final_return_pct: float = 0.0        # equity vs start, in percent
    trading_days: int = 0
    note: str = ""


def evaluate_daily_equity(
    start_balance: float,
    daily_equity: Sequence[float],
    criteria: PropFirmCriteria,
) -> EvalResult:
    """Walk a day-by-day equity curve and decide pass / breach / in-progress.

    ``daily_equity[i]`` is the account equity at the *close of day i* (the
    sequence should NOT include the starting balance as day 0 — it is end-of-day
    marks). The walk is strictly left-to-right (no look-ahead):

    For each day we check, in order:
      1. max daily loss — (prev_equity - today_equity) / start  > max_daily_loss
      2. max total drawdown — (start - today_equity) / start > max_total_drawdown
    The first day that violates either => BREACHED at that day.

    After the walk, if the profit target was reached on/by the last day AND the
    minimum trading-days requirement is met => PASSED; otherwise IN_PROGRESS.

    Reaching the profit target does not retroactively erase an earlier breach:
    a breach on any prior day ends the evaluation immediately.
    """
    if start_balance <= 0:
        raise ValueError("start_balance must be positive")

    prev = start_balance
    peak_return = 0.0
    n_days = len(daily_equity)

    for day, equity in enumerate(daily_equity):
        daily_loss_pct = (prev - equity) / start_balance * 100.0
        if daily_loss_pct > criteria.max_daily_loss_pct:
            return EvalResult(
                outcome=EvalOutcome.BREACHED,
                breach=BreachKind.MAX_DAILY_LOSS,
                breach_day=day,
                final_return_pct=(equity - start_balance) / start_balance * 100.0,
                trading_days=day + 1,
                note=f"day {day}: lost {daily_loss_pct:.2f}% in one day "
                     f"(limit {criteria.max_daily_loss_pct:.2f}%)",
            )

        total_dd_pct = (start_balance - equity) / start_balance * 100.0
        if total_dd_pct > criteria.max_total_drawdown_pct:
            return EvalResult(
                outcome=EvalOutcome.BREACHED,
                breach=BreachKind.MAX_TOTAL_DRAWDOWN,
                breach_day=day,
                final_return_pct=(equity - start_balance) / start_balance * 100.0,
                trading_days=day + 1,
                note=f"day {day}: drawdown {total_dd_pct:.2f}% from start "
                     f"(limit {criteria.max_total_drawdown_pct:.2f}%)",
            )

        ret_pct = (equity - start_balance) / start_balance * 100.0
        peak_return = max(peak_return, ret_pct)
        prev = equity

    final_return_pct = (
        (daily_equity[-1] - start_balance) / start_balance * 100.0 if n_days else 0.0
    )
    target_hit = peak_return >= criteria.profit_target_pct
    days_ok = n_days >= criteria.min_trading_days

    if target_hit and days_ok:
        return EvalResult(
            outcome=EvalOutcome.PASSED,
            final_return_pct=final_return_pct,
            trading_days=n_days,
            note=f"profit target {criteria.profit_target_pct:.2f}% reached "
                 f"in {n_days} day(s)",
        )

    missing = []
    if not target_hit:
        missing.append(
            f"target {criteria.profit_target_pct:.2f}% not yet reached "
            f"(peak {peak_return:.2f}%)"
        )
    if not days_ok:
        missing.append(
            f"need {criteria.min_trading_days} trading days, have {n_days}"
        )
    return EvalResult(
        outcome=EvalOutcome.IN_PROGRESS,
        final_return_pct=final_return_pct,
        trading_days=n_days,
        note="; ".join(missing),
    )


def equity_curve_from_trades(
    start_balance: float,
    trade_pnls: Sequence[float],
) -> List[float]:
    """Turn a sequence of per-trade P&L (cash) into a cumulative equity curve.

    Convenience for callers who have a trade list rather than daily marks. Each
    element of the result is the running balance after that trade. Treat each
    trade as its own "day" only if your firm's daily-loss rule is per-trade;
    otherwise aggregate trades per day before calling
    :func:`evaluate_daily_equity`.
    """
    curve: List[float] = []
    bal = start_balance
    for pnl in trade_pnls:
        bal += pnl
        curve.append(bal)
    return curve


def check_consistency(
    lot_sizes: Sequence[float],
    max_deviation_pct: float = 0.0,
) -> EvalResult:
    """Flag a consistency-rule breach (ep 39).

    > "A consistency rule is basically you need to use the same amount of lot
    > sizes over and over and over. If that doesn't happen, then they can remove
    > you from the account."

    The transcript gives no numeric tolerance, so the default is *exact*
    sameness (``max_deviation_pct == 0`` -> any difference from the modal/most
    common lot size is a breach). Pass a tolerance (percent of the reference lot)
    if your firm allows drift. Returns BREACHED at the first offending trade or
    IN_PROGRESS if consistent. The instructor's actual advice is to AVOID firms
    with this rule (``no_consistency_rule=True``); this checker exists for when
    you cannot.
    """
    if not lot_sizes:
        return EvalResult(outcome=EvalOutcome.IN_PROGRESS, note="no trades")

    # Reference = most common lot size.
    ref = max(set(lot_sizes), key=list(lot_sizes).count)
    tol = abs(ref) * max_deviation_pct / 100.0
    for i, lot in enumerate(lot_sizes):
        if abs(lot - ref) > tol:
            return EvalResult(
                outcome=EvalOutcome.BREACHED,
                breach=BreachKind.CONSISTENCY,
                breach_day=i,
                note=f"trade {i}: lot {lot} deviates from reference {ref} "
                     f"(tolerance {max_deviation_pct:.2f}%)",
            )
    return EvalResult(outcome=EvalOutcome.IN_PROGRESS, note="lot sizes consistent")


def payout_target_hit(
    start_balance: float,
    equity: float,
    payout_pct: float = 2.0,
) -> bool:
    """Has the account gained enough to take the instructor's small payout?

    > "you don't need to get a payout of 10%, 15%. No, a 2% payout is fine ...
    > Just get that payout and that refund from the fee that you paid for that
    > challenge."  — ep 39

    Default target is 2% of the starting balance. Returns True once equity is
    at/above that. The doctrine is explicitly *small and repeatable*: take the
    2% + fee refund, buy another account, repeat — "treat it like a business".
    """
    if start_balance <= 0:
        raise ValueError("start_balance must be positive")
    gain_pct = (equity - start_balance) / start_balance * 100.0
    return gain_pct >= payout_pct

"""Pre-trading readiness checklist — A-Z Guide ep 38 & ep 39 (files 039, 040).

Ep 38 ("Things You NEED to know before You Start Trading") and ep 39 ("Guide to
Get Funded") are almost entirely mindset/business. The one thing that is cleanly
*codifiable* from them is the instructor's enumerated list of "things you need to
know / steps to get funded" — captured here as an ordered enum of structured
items, each quoting the transcript. This is a structured representation of
narrative content, NOT a price/risk calculation.

Each :class:`ReadinessItem` carries the lesson, the episode it comes from, and
the verbatim quote. :func:`print_checklist` renders them; :func:`ready_to_trade`
applies the few items that can be answered yes/no before risking money.

NARRATIVE-ONLY caveat: the *truth* of these lessons cannot be machine-verified
(e.g. "follow one mentor religiously"). The boolean gate in
:func:`ready_to_trade` only checks the handful of concrete prerequisites the
instructor names as required before forward-testing real money: a written
trading plan, a chosen single mentor, a chosen firm/broker, and a defined risk
plan. Everything else prints as guidance.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List


class Episode(Enum):
    EP38_BEFORE_YOU_START = "ep 38 — Things You NEED to know before You Start Trading (file 039)"
    EP39_GET_FUNDED = "ep 39 — Guide to Get Funded / Make Money (file 040)"


@dataclass(frozen=True)
class ReadinessItem:
    """One enumerated lesson / step, with its source episode and verbatim quote."""

    order: int
    title: str
    episode: Episode
    quote: str
    # True if this item is a hard prerequisite that can be answered yes/no
    # before risking real money (used by ``ready_to_trade``).
    gating: bool = False


# Ep 38 — "things you need to know before you start trading" (mindset rules) and
# Ep 39 — the enumerated "steps to get funded". Order follows the transcripts.
CHECKLIST: List[ReadinessItem] = [
    ReadinessItem(
        order=1,
        title="Don't backtest — forward test and hindsight-only",
        episode=Episode.EP38_BEFORE_YOU_START,
        quote="don't back test ... there's no need to backtest at all zero reason "
              "to backtest forward test and hindsight backtest ... you will never "
              "learn the emotional lessons that you need to learn in live trading.",
    ),
    ReadinessItem(
        order=2,
        title="Follow ONE mentor religiously",
        episode=Episode.EP38_BEFORE_YOU_START,
        quote="follow one mentor ... As long as you follow that mentor religiously "
              "... don't listen to what anyone else besides your mentor is telling you.",
        gating=True,
    ),
    ReadinessItem(
        order=3,
        title="Stay off social media while trading",
        episode=Episode.EP38_BEFORE_YOU_START,
        quote="you don't want to be active on social media because you don't want "
              "your mind to get affected by other mentors ... you will activate "
              "your shiny object syndrome.",
    ),
    ReadinessItem(
        order=4,
        title="Jump into the deep end — learn through experience / pain",
        episode=Episode.EP38_BEFORE_YOU_START,
        quote="you learn through experience and you jump into the deep end ... you "
              "will lose. You will lose ... you need to lose you need to fail in "
              "order to win.",
    ),
    ReadinessItem(
        order=5,
        title="Don't idolize and don't rely on anyone",
        episode=Episode.EP38_BEFORE_YOU_START,
        quote="don't idolize ... that is also the reason why you never want to "
              "idolize someone nobody here is a god ... it's all up to you to be "
              "successful no one else.",
    ),
    ReadinessItem(
        order=6,
        title="Never change the CORE of your strategy",
        episode=Episode.EP38_BEFORE_YOU_START,
        quote="we never change the core of our strategy ... treat them like a tree "
              "... you want to water the same tree ... never change the core of "
              "your strategy.",
    ),
    ReadinessItem(
        order=7,
        title="Submit to time (following the right instructions)",
        episode=Episode.EP38_BEFORE_YOU_START,
        quote="the only thing holding you back is time ... submitting to time only "
              "works if you are submitting to the right thing.",
    ),
    ReadinessItem(
        order=8,
        title="Learning more does not equal making more money",
        episode=Episode.EP38_BEFORE_YOU_START,
        quote="learning more does not equate to making more money ... People are "
              "too focused on trying to figure out an algorithm instead of making "
              "money.",
    ),
    ReadinessItem(
        order=9,
        title="Have a written trading plan (know when/where to enter)",
        episode=Episode.EP39_GET_FUNDED,
        quote="if you don't have your training plan set in stone then ... it's "
              "futile to blame psychology ... once we have our training plan we "
              "know when and where to enter then you can only fail through your "
              "psychology or your risk management.",
        gating=True,
    ),
    ReadinessItem(
        order=10,
        title="Choose a firm or broker (no consistency rule, ~1:100 leverage)",
        episode=Episode.EP39_GET_FUNDED,
        quote="a firm, a prop firm. Or if you want to trade your personal account "
              "... a broker ... look for a prop firm with no consistency rule ... "
              "preferably a prop firm with one to 100.",
        gating=True,
    ),
    ReadinessItem(
        order=11,
        title="Risk management with risk parameters — lower risk in drawdown",
        episode=Episode.EP39_GET_FUNDED,
        quote="risk management is extremely important ... you want to have risk "
              "parameters ... when am I dropping my risk to 0.5%? ... 0.25%? ... "
              "You always want to lower your risk.",
        gating=True,
    ),
    ReadinessItem(
        order=12,
        title="Aim for 1:2 RR at ~40-50% win rate",
        episode=Episode.EP39_GET_FUNDED,
        quote="Just aim for a 1 to 2 RR with around even a 50%, 40% win rate ... "
              "50% win rate, 1 to 2 RR, you can't fail.",
    ),
    ReadinessItem(
        order=13,
        title="Take a small 2% payout — treat it like a business",
        episode=Episode.EP39_GET_FUNDED,
        quote="you don't need to get a payout of 10%, 15%. No, a 2% payout is fine "
              "... treat it like a business ... from the 2% payout and the refund "
              "you buy another one and then you repeat the process.",
    ),
    ReadinessItem(
        order=14,
        title="Never fall into shiny-object syndrome",
        episode=Episode.EP39_GET_FUNDED,
        quote="never SOS ... never fall into the trap shiny object syndrome ... if "
              "you do that I can guarantee you you will never be funded.",
    ),
]


@dataclass
class ReadinessState:
    """Caller-supplied answers to the few hard prerequisites (gating items)."""

    has_written_trading_plan: bool = False   # item 9
    has_single_mentor: bool = False          # item 2
    has_chosen_firm_or_broker: bool = False  # item 10
    has_risk_plan: bool = False              # item 11


def gating_items() -> List[ReadinessItem]:
    """The subset of the checklist that is a concrete yes/no prerequisite."""
    return [i for i in CHECKLIST if i.gating]


def ready_to_trade(state: ReadinessState) -> bool:
    """True only if every hard prerequisite the instructor names is satisfied.

    The four gating items map one-to-one to ``ReadinessState`` fields. The
    instructor is explicit that these must precede risking real money — e.g.
    "once we have our training plan ... then you can only fail through your
    psychology or your risk management" (ep 39). The non-gating items are
    mindset guidance and are not machine-checkable.
    """
    return (
        state.has_written_trading_plan
        and state.has_single_mentor
        and state.has_chosen_firm_or_broker
        and state.has_risk_plan
    )


def print_checklist() -> None:
    """Print the full ordered checklist with episode tags and quotes."""
    print("A-Z Guide — pre-trading / get-funded readiness checklist")
    print("=" * 70)
    for item in CHECKLIST:
        gate = "  [GATING]" if item.gating else ""
        print(f"{item.order:>2}. {item.title}{gate}")
        print(f"    ({item.episode.value})")
        print(f'    "{item.quote}"')
        print()

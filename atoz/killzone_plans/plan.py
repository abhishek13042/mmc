"""Session trading plans — common engine (A-Z Guide ep 29 & ep 30).

This module is the shared machinery behind the **London Killzone Trading Plan**
(ep 29) and the **New York Killzone Trading Plan** (ep 30). Both episodes
describe the *exact same* mechanical sequence; the instructor is emphatic:

> "the new york retracement is the exact same thing as the asia expansion and
>  the new york reversal is the exact same thing as your asia consolidation the
>  only thing that changes is the time ... you do the exact same thing the only
>  thing that change is the time."  — ep 30

The mechanical plan, fractally:

1. HTF context / bias. The hard work is done on the higher time frame:
   > "the only thing you are doing on the lower tier frame is you are getting in
   >  sync with price on the higher time frame ... the hard work is done on the
   >  higher time frame ... if we move from that premium array on the four hour
   >  that order block what is our target ... this swing low on the four hour ...
   >  premium array to discount array."  — ep 29
   We encode the bias as a :class:`Direction` (BEARISH = trading a premium→
   discount leg, sell; BULLISH = discount→premium, buy).

2. Inside the **session killzone window** (London / New York, broker/EET time)
   we need a *new* displacement (a fair value gap) in the bias direction:
   > "all i need to see in London is a new bearish fair value gap. I enter on
   >  the overlapping PDA."  — ep 29
   We objectify a setup as a sweep→displacement entry (ep 12 ``find_entries``)
   whose displacement FVG confirms *inside* the session window and agrees with
   the bias.

3. Entry = the displacement FVG edge (the "overlapping PDA"); stop = the swept
   swing ("cover the intermediate term high / low"); target = the opposing 4H
   PD array. ``find_entries`` already returns exactly this triple (FLOD entry /
   LLOD stop / opposing PD-array target, ep 9 + ep 12).

4. Two variations, distinguished by what the *previous* session already did:
     * **expansion / retracement** — the previous session already displaced in
       the bias direction (Asia already had bearish FVGs, or London already made
       the low of the day). A single new FVG in the session is enough.
         > "if asia already has bearish fair value gaps that is perfectly fine
         >  ... all i need to see in London is a new bearish fair value gap."  — ep 29
         > "if london makes the low of the day and new york respects that low
         >  then you have a new york retracement."  — ep 30
     * **consolidation / reversal** — the previous session did *not* displace in
       the bias direction; the session itself comes into the HTF PD array and
       builds the SD model (the classic 1-2-FVG sequence):
         > "we need bearish fair value gaps being created in London itself ...
         >  you have a first bearish fair value gap and you wait for a second one
         >  ... that is again your sd model then that right there that is your
         >  entry."  — ep 29
         > "this is a new york reversal ... the london low was right there ...
         >  london didn't make the low of the day."  — ep 30
   ``classify_session_variation`` labels which one a setup is; the London / NY
   detector modules wrap this engine with the correct killzone and variation
   names.

No look-ahead: every check uses only bars at or before the bar that confirms
the entry FVG (``Entry.index`` == FVG c3). Pure functions over an OHLC
DataFrame with a broker-time (EET) DatetimeIndex.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import pandas as pd

from atoz.core import Candles, Direction, Swing, find_swings
from atoz.entries import Entry, find_entries
from atoz.timing import Killzone, NY_TO_BROKER, killzone_of_broker


class SessionVariation(Enum):
    """The two day-profile variations every session plan has (ep 29 / ep 30).

    The names are paired across sessions because the instructor insists they are
    mechanically identical, differing only in *which* session is acting:

    * ``EXPANSION`` — London-plan "Asia expansion" / NY-plan "New York
      retracement": the prior session already displaced in the bias direction,
      so a single new session FVG is enough.
    * ``CONSOLIDATION`` — London-plan "Asia consolidation" / NY-plan "New York
      reversal": the session itself comes into the HTF PD array and builds the
      SD model (1st FVG, then a 2nd confirming FVG).
    """

    EXPANSION = "expansion"          # Asia expansion / NY retracement
    CONSOLIDATION = "consolidation"  # Asia consolidation / NY reversal


@dataclass
class SessionSetup:
    """A faithful session-plan setup (ep 29 / ep 30).

    Wraps an ep-12 :class:`~atoz.entries.Entry` with the session context the two
    trading-plan videos add: which killzone it fired in, which day-profile
    variation it is, and the timestamp of the confirming bar.
    """

    session: Killzone                # LONDON or NEW_YORK (the killzone it fired in)
    variation: SessionVariation
    direction: Direction             # bias direction (BEARISH = sell leg)
    entry_price: float               # overlapping PDA / FVG edge (FLOD)
    stop_loss: float                 # the covered ITH/ITL swing (LLOD)
    take_profit: float               # opposing 4H PD array
    time: pd.Timestamp               # bar that confirms the entry FVG (c3)
    entry: Entry                     # the underlying ep-12 entry

    @property
    def rr(self) -> float:
        return self.entry.rr


def _session_mask(df: pd.DataFrame, session: Killzone) -> pd.Series:
    """Boolean Series: True where the bar falls inside ``session``'s killzone.

    Broker/EET time (ep 16 note: broker = NY + 7 constant). London 09:00-12:00,
    New York 14:00-17:00 broker time.
    """
    hours = df.index.hour + df.index.minute / 60.0
    return pd.Series([killzone_of_broker(h) is session for h in hours], index=df.index)


def _displaced_before(
    df: pd.DataFrame,
    setup_index: int,
    direction: Direction,
    session_start_pos: int,
    fvgs,
) -> bool:
    """Did the *previous* session already displace into the HTF array and make
    the running extreme in the bias direction?

    The two videos distinguish the variations by *where the prior session's
    extreme is*, not merely by the presence of an FVG:

    > "if london makes the low of the day and new york respects that low then you
    >  have a new york retracement ... london didn't make the low of the day [→
    >  reversal]."  — ep 30

    So EXPANSION (Asia-expansion / NY-retracement) requires **two** things in the
    run-up window (the previous session), using only bars before the session
    opens (no look-ahead):

    1. a same-direction displacement (an FVG in the bias direction) — Asia/London
       "already had bearish fair value gaps" / "already had a displacement";
    2. the previous session made the **running extreme** of the day in the bias
       direction (the low of the day for a bearish/sell bias, the high of the day
       for a bullish/buy bias) — "london makes the low of the day".

    If either is missing the session itself is the one reaching into the HTF array
    → CONSOLIDATION / reversal.
    """
    lo = max(0, session_start_pos - _LOOKBACK_BARS)
    if lo >= session_start_pos:
        return False

    c = Candles.of(df)
    bearish = direction is Direction.BEARISH

    # 1) prior-session displacement in the bias direction
    has_disp = any(
        f.direction is direction and lo <= f.c3_index < session_start_pos
        for f in fvgs
    )
    if not has_disp:
        return False

    # 2) prior session made the running extreme of the day in the bias direction.
    #    Compare the prior-session extreme against the session-so-far extreme: the
    #    prior session "made the low/high of the day" if its extreme is not
    #    exceeded by the session up to the setup bar.
    if bearish:
        prior_ext = float(c.low[lo:session_start_pos].min())
        sess_ext = float(c.low[session_start_pos:setup_index + 1].min())
        return prior_ext <= sess_ext
    prior_ext = float(c.high[lo:session_start_pos].max())
    sess_ext = float(c.high[session_start_pos:setup_index + 1].max())
    return prior_ext >= sess_ext


# bars of prior price action that count as "the previous session".
# 48 M15 bars = 12h, comfortably spanning the immediately-preceding session.
_LOOKBACK_BARS = 48


def classify_session_variation(
    df: pd.DataFrame,
    setup: Entry,
    session_start_pos: int,
    fvgs,
) -> SessionVariation:
    """Label a setup EXPANSION vs CONSOLIDATION (ep 29 / ep 30).

    EXPANSION (Asia-expansion / NY-retracement): the previous session already
    displaced in the bias direction. CONSOLIDATION (Asia-consolidation /
    NY-reversal): it did not, so the session itself builds the SD model.
    """
    if _displaced_before(df, setup.index, setup.direction, session_start_pos, fvgs):
        return SessionVariation.EXPANSION
    return SessionVariation.CONSOLIDATION


def _first_session_pos(df: pd.DataFrame, session: Killzone, day, mask: pd.Series) -> int:
    """iloc position of the first bar of ``session`` on calendar ``day``."""
    same_day = (df.index.normalize() == day) & mask.to_numpy()
    where = same_day.nonzero()[0] if hasattr(same_day, "nonzero") else \
        pd.Series(same_day).to_numpy().nonzero()[0]
    return int(where[0]) if len(where) else 0


def find_session_setups(
    df: pd.DataFrame,
    session: Killzone,
    bias: Optional[Direction] = None,
    swings: Optional[List[Swing]] = None,
    confirm_window: int = 15,
) -> List[SessionSetup]:
    """Find session-plan setups inside ``session``'s killzone window.

    The shared engine for ep 29 (London) and ep 30 (New York). For every
    sweep→displacement entry (ep 12) whose confirming FVG falls inside the
    session window and agrees with ``bias`` (if given), emit a
    :class:`SessionSetup` carrying the killzone, the day-profile variation
    (EXPANSION vs CONSOLIDATION) and the entry triple.

    Parameters
    ----------
    session : Killzone
        ``Killzone.LONDON`` or ``Killzone.NEW_YORK``.
    bias : Direction, optional
        The HTF bias (premium→discount = BEARISH). If ``None``, both directions
        are accepted (the engine reports the direction of each setup). The
        videos always set bias from the 4H/HTF first.
    confirm_window : int
        Passed through to ``find_entries`` (ep 12): how soon after the sweep the
        displacement FVG must confirm.
    """
    if session not in (Killzone.LONDON, Killzone.NEW_YORK):
        raise ValueError("session must be Killzone.LONDON or Killzone.NEW_YORK")

    if swings is None:
        swings = find_swings(df)
    entries = find_entries(df, swings=swings, confirm_window=confirm_window)

    from atoz.core import find_fvgs
    fvgs = find_fvgs(df)

    mask = _session_mask(df, session)
    mask_arr = mask.to_numpy()
    days = df.index.normalize()

    out: List[SessionSetup] = []
    for e in entries:
        # the entry FVG must CONFIRM inside the session killzone window
        if not bool(mask_arr[e.index]):
            continue
        if bias is not None and e.direction is not bias:
            continue

        day = days[e.index]
        session_start_pos = _first_session_pos(df, session, day, mask)
        variation = classify_session_variation(df, e, session_start_pos, fvgs)

        out.append(
            SessionSetup(
                session=session,
                variation=variation,
                direction=e.direction,
                entry_price=e.entry_price,
                stop_loss=e.stop_loss,
                take_profit=e.take_profit,
                time=df.index[e.index],
                entry=e,
            )
        )

    out.sort(key=lambda s: s.time)
    return out

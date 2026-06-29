"""The :class:`ContextArea` — the objective area where we look for an entry
(transcript 10 — Usual & Unusual Context).

Context = from a **boundary** (a narrative PD array we enter *from* — an FVG,
FVA or swing point) to the **target** (the first opposing PD array we trade
*towards*). As soon as price trades into the boundary we drop to the lower
timeframe to look for entry confirmation, and we keep looking until the target
is reached. After the target is taken we stop until *new* context forms
(transcript 10, ~3:10 / ~9:29 — context highs/lows are often swept).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

from mmc.core import Direction, FairValueArea, FairValueGap, SwingPoint, Zone

# The boundary is always a price *zone* we enter from (FVG / FVA / a synthetic
# swing-or-previous-candle zone). The target can be a swing point or a zone.
Boundary = Zone
Target = Union[SwingPoint, Zone]

# Which last-line-of-defense / defense produced the area (transcript 04 / 10).
Defense = str  # "FLOD" | "ODD" | "LOD"
Kind = str     # "usual" | "unusual"


def _target_price(target: Target) -> float:
    """The price level a target sits at (a swing's price, else a zone edge)."""
    if isinstance(target, SwingPoint):
        return target.price
    # For a zone target we use the near edge in the move's favour. Callers pass
    # the relevant edge via a SwingPoint where possible; for a zone we take the
    # midpoint as a neutral reference.
    return target.midpoint


@dataclass
class ContextArea:
    """An objective context area (transcript 10).

    ``boundary``   the PD array we enter *from* (a :class:`Zone` — FVG / FVA /
                   swing-or-previous-candle zone). Price trading into it is the
                   trigger to drop a timeframe.
    ``target``     the first opposing PD array we trade *towards* (a
                   :class:`SwingPoint` or :class:`Zone`).
    ``direction``  polarity we expect to continue in (the boundary's polarity):
                   bullish = trade up from a discount boundary towards a premium
                   target; bearish is the mirror.
    ``kind``       "usual" (always traded) or "unusual" (the FVA-seeking-
                   liquidity bigger picture; the FVG inside it is still usual).
    ``defense``    which defense produced the area: "FLOD" (FVG boundary),
                   "ODD" (FVA boundary) or "LOD" (swing / previous-candle
                   boundary).
    ``external_target`` an optional further-away target (transcript 10, ~2:54 —
                   "we can still have a different target all the way towards the
                   left"); for unusual context this is the FVA's far side.
    """

    boundary: Boundary
    target: Target
    direction: Direction
    kind: Kind = "usual"
    defense: Defense = "FLOD"
    external_target: Optional[Target] = None

    # ------------------------------------------------------------------ #
    # Geometry helpers
    # ------------------------------------------------------------------ #

    @property
    def target_price(self) -> float:
        return _target_price(self.target)

    @property
    def is_bullish(self) -> bool:
        return self.direction is Direction.BULLISH

    def price_in_boundary(self, price: float) -> bool:
        """True if ``price`` sits inside the boundary zone — the trigger to drop
        to the lower timeframe and start looking for an entry (transcript 10,
        ~1:57 — "as soon as we trade back into that fair value gap")."""
        return self.boundary.contains(price)

    def bar_in_boundary(self, df, index: int) -> bool:
        """True if the bar at integer position ``index`` trades into the
        boundary (its high/low range overlaps the boundary band)."""
        low = float(df["low"].to_numpy()[index])
        high = float(df["high"].to_numpy()[index])
        return high >= self.boundary.bottom and low <= self.boundary.top

    def contains_entry_zone(self, zone: Zone) -> bool:
        """True if a candidate lower-timeframe entry ``zone`` lies inside this
        context area — i.e. between the boundary and the target, on the correct
        side. We only look for entries *within* context (transcript 10)."""
        if self.is_bullish:
            # Entries sit above the discount boundary and below the premium
            # target as price works up.
            lo = self.boundary.bottom
            hi = self.target_price
        else:
            lo = self.target_price
            hi = self.boundary.top
        return lo <= zone.bottom and zone.top <= hi

    def target_reached(self, df) -> bool:
        """True once a bar after the boundary trades to/through the target —
        after which we stop looking for entries (transcript 10, ~3:10)."""
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        start = self.boundary.index + 1
        tgt = self.target_price
        for j in range(start, len(df)):
            if self.is_bullish and highs[j] >= tgt:
                return True
            if not self.is_bullish and lows[j] <= tgt:
                return True
        return False

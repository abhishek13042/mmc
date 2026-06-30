"""Market Maker Model — MMBM / MMSM (A-Z Guide ep 34, transcript 035).

> "You are moving from a discount array to the first premium array ... in between
> that, this price action, that is where you want to get involved. This is your
> market maker buy model." A buy model (MMBM) runs from a discount array (the
> low / curve turn) up to a premium array (the target = draw on liquidity); the
> sell model (MMSM) is the mirror.
>
> The start of the model is an **ST** — "a fair value gap higher ... that is
> already an early indication of the intermediate-term low being confirmed". The
> ST forms the *curve turn* (the low of a buy model, the high of a sell model).
>
> After the ST, price advances as a sequence of **short-term ranges** that "hold"
> one after another toward the target. Critically: "a short term range needs to
> have a fair value gap ... otherwise it isn't a short term range." Each holding
> short-term range is an entry. Reclaimed order blocks form on the first curve.
>                                                                        — ep 34

Mechanical detection over an OHLC DataFrame (DatetimeIndex; ``index`` = iloc
position). Pure functions, no look-ahead: a model is only emitted once its target
(the premium/discount array that defines the context) has been reached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import pandas as pd

from atoz.core.fvg import FVG, find_fvgs
from atoz.core.swings import find_swings, swing_highs, swing_lows
from atoz.core.types import Candles, Direction, Swing, SwingType
from atoz.blocks import PDArray, find_reclaimed_order_blocks


class ModelType(Enum):
    """The two market maker models (ep 34)."""

    BUY = "buy"     # MMBM — discount array (low / curve turn) → premium array target
    SELL = "sell"   # MMSM — premium array (high / curve turn) → discount array target

    @property
    def direction(self) -> Direction:
        return Direction.BULLISH if self is ModelType.BUY else Direction.BEARISH


class Phase(Enum):
    """The legs of the model (ep 34 — consolidation → manipulation → expansion;
    AMD vocabulary from ep 18)."""

    CONSOLIDATION = "consolidation"   # "this being a consolidation ... least relevant"
    MANIPULATION = "manipulation"     # the move that sets the curve turn (the ST origin)
    EXPANSION = "expansion"           # the distribution leg toward the target


@dataclass
class ShortTermRange:
    """A short-term range inside the model (ep 34).

    "A short term range needs to have a fair value gap ... otherwise it isn't a
    short term range." Each holding short-term range is an entry; it ideally also
    comes off a previous discount array.
    """

    index: int                 # bar index of the defining fair value gap (middle candle)
    fvg: FVG                   # the fair value gap that makes it a short-term range
    top: float
    bottom: float
    direction: Direction
    held: bool = False         # did price respect it on the way to target?

    @property
    def is_entry(self) -> bool:
        """A holding short-term range with an FVG is an entry (ep 34)."""
        return self.held


@dataclass
class Curve:
    """One of the model's two curves (ep 34 / ep 6).

    The market maker model is "two curves": the first (accumulation) curve and
    the second (distribution) curve. Reclaimed order blocks form on the first
    curve; the curve turn is where they meet (the model low for a buy model).
    """

    direction: Direction       # BULLISH = a rising (distribution) curve, etc.
    start_index: int
    end_index: int
    start_price: float
    end_price: float


@dataclass
class MarketMakerModel:
    """A detected market maker model (ep 34).

    The context is a move from a ``origin`` array (discount for a buy model) to a
    ``target`` array (premium for a buy model = the draw on liquidity). The model
    is the price action in between: an ST (curve turn) then a chain of holding
    short-term ranges into the target.
    """

    model_type: ModelType
    origin_index: int          # the discount(buy)/premium(sell) array — context origin
    origin_price: float
    curve_turn_index: int      # the model low (buy) / high (sell) — the ST's swing
    curve_turn_price: float
    target_index: int          # bar at which the premium/discount target was reached
    target_price: float        # the premium array (buy) / discount array (sell)
    st_fvg: FVG                # the fair value gap that confirmed the curve turn (the ST)
    short_term_ranges: List[ShortTermRange] = field(default_factory=list)
    first_curve: Optional[Curve] = None   # accumulation curve (before the turn)
    second_curve: Optional[Curve] = None  # distribution curve (turn → target)
    reclaimed_obs: List[PDArray] = field(default_factory=list)

    @property
    def direction(self) -> Direction:
        return self.model_type.direction

    @property
    def entries(self) -> List[ShortTermRange]:
        """Holding short-term ranges = the entries (ep 34)."""
        return [r for r in self.short_term_ranges if r.is_entry]

    def phase_at(self, i: int) -> Optional[Phase]:
        """Label the phase of bar ``i`` within this model (ep 34/18)."""
        if i < self.curve_turn_index:
            # before the turn — the manipulation that creates the curve turn,
            # preceded by consolidation.
            if i < self.origin_index:
                return None
            return Phase.MANIPULATION
        if i <= self.target_index:
            return Phase.EXPANSION
        return None


def _confirms_turn(c: Candles, fvg: FVG, model_type: ModelType) -> bool:
    """An ST fair value gap that confirms the curve turn must be in the model's
    direction (a bullish FVG "higher" confirms a buy-model low) — ep 34."""
    return fvg.direction is model_type.direction


def find_short_term_ranges(
    df: pd.DataFrame,
    start_index: int,
    end_index: int,
    direction: Direction,
    fvgs: Optional[List[FVG]] = None,
) -> List[ShortTermRange]:
    """All short-term ranges between ``start_index`` and ``end_index`` (ep 34).

    A short-term range is defined by a fair value gap of the model's direction.
    It is marked ``held`` if price never closed fully back through the gap before
    the model's target was reached (i.e. it "held" — ep 34).
    """
    c = Candles.of(df)
    if fvgs is None:
        fvgs = find_fvgs(df)

    out: List[ShortTermRange] = []
    for f in fvgs:
        if f.direction is not direction:
            continue
        if not (start_index <= f.index <= end_index):
            continue

        # "held" = not fully disrespected (no close through the far side) before
        # the model target. For a bullish range, a close below the bottom breaks it.
        held = True
        for k in range(f.c3_index + 1, min(c.n, end_index + 1)):
            if direction is Direction.BULLISH and c.close[k] < f.bottom:
                held = False
                break
            if direction is Direction.BEARISH and c.close[k] > f.top:
                held = False
                break

        out.append(
            ShortTermRange(
                index=f.index, fvg=f, top=f.top, bottom=f.bottom,
                direction=direction, held=held,
            )
        )

    out.sort(key=lambda r: r.index)
    return out


def find_market_maker_models(
    df: pd.DataFrame,
    swings: Optional[List[Swing]] = None,
    swing_strength: int = 2,
) -> List[MarketMakerModel]:
    """Detect market maker buy/sell models over ``df`` (ep 34).

    Algorithm (faithful to the transcript's mechanical steps):

    1. **Context** — a buy model runs from a swing low (the discount-array origin /
       curve turn) up to the next swing high that is taken (the premium array =
       target = draw on liquidity). A sell model is the mirror (high → low).
    2. **ST / curve turn** — the model is only valid if a fair value gap *in the
       model's direction* forms after the turn ("a fair value gap higher ... the
       intermediate-term low being confirmed"). The earliest such FVG is the ST.
    3. **Short-term ranges** — every directional FVG between the turn and the
       target is a short-term range; holding ones are entries.
    4. **Curves** — the first (accumulation) curve runs into the turn; the second
       (distribution) curve runs from the turn to the target. Reclaimed order
       blocks that formed on the first curve are attached.

    No look-ahead: a model is emitted only once its target swing was actually
    taken by a later bar.
    """
    c = Candles.of(df)
    if swings is None:
        swings = find_swings(df, strength=swing_strength)
    fvgs = find_fvgs(df)
    reclaimed = find_reclaimed_order_blocks(df)

    ordered = sorted(swings, key=lambda s: s.index)
    models: List[MarketMakerModel] = []

    for turn in ordered:
        if turn.kind is SwingType.LOW:
            model_type = ModelType.BUY
        else:
            model_type = ModelType.SELL
        direction = model_type.direction

        # --- target: the first opposing swing AFTER the turn, that price reaches.
        target_swing = next(
            (s for s in ordered
             if s.index > turn.index and s.kind is not turn.kind),
            None,
        )
        if target_swing is None:
            continue

        # No look-ahead: confirm the target was actually taken by a later bar.
        target_taken_at = None
        for k in range(target_swing.index, c.n):
            if model_type is ModelType.BUY and c.high[k] >= target_swing.price:
                target_taken_at = k
                break
            if model_type is ModelType.SELL and c.low[k] <= target_swing.price:
                target_taken_at = k
                break
        if target_taken_at is None:
            continue

        # --- ST: earliest directional FVG after the turn (the curve turn confirm).
        st = next(
            (f for f in fvgs
             if f.index > turn.index and f.index <= target_swing.index
             and _confirms_turn(c, f, model_type)),
            None,
        )
        if st is None:
            continue

        # --- origin: the opposing swing just BEFORE the turn = the context origin
        # (the discount array a buy model rises from / premium a sell model falls
        # from). Falls back to the turn itself if none precedes it.
        origin_swing = next(
            (s for s in reversed(ordered)
             if s.index < turn.index and s.kind is not turn.kind),
            turn,
        )

        ranges = find_short_term_ranges(
            df, turn.index, target_swing.index, direction, fvgs
        )

        first_curve = Curve(
            direction=direction.opposite,
            start_index=origin_swing.index, end_index=turn.index,
            start_price=origin_swing.price, end_price=turn.price,
        )
        second_curve = Curve(
            direction=direction,
            start_index=turn.index, end_index=target_taken_at,
            start_price=turn.price, end_price=target_swing.price,
        )

        # reclaimed OBs that formed on the first curve (origin → turn) — ep 6/34.
        obs_on_curve = [
            ob for ob in reclaimed
            if origin_swing.index <= ob.index <= turn.index
        ]

        models.append(
            MarketMakerModel(
                model_type=model_type,
                origin_index=origin_swing.index, origin_price=origin_swing.price,
                curve_turn_index=turn.index, curve_turn_price=turn.price,
                target_index=target_taken_at, target_price=target_swing.price,
                st_fvg=st,
                short_term_ranges=ranges,
                first_curve=first_curve, second_curve=second_curve,
                reclaimed_obs=obs_on_curve,
            )
        )

    models.sort(key=lambda m: m.curve_turn_index)
    return models

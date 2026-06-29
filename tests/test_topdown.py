"""Tests for the top-down layer (transcript 12).

Uses short, strictly-monotonic synthetic frames so that *only* the candle-science
argument fires (no swings -> no order flow lags, no intermediate-term structure).
That gives precise, deterministic control over the accumulated bias.
"""

from mmc.core.types import Direction, Timeframe
from mmc.topdown import (
    Bias,
    StyleConfig,
    TraderStyle,
    best_pair,
    compute_bias,
    filter_pairs,
    rank_score,
    style_config,
    top_down,
)


def _rising(n=5):
    """Strictly increasing bullish candles (small wicks) -> bullish last candle,
    no interior swing points."""
    bars = []
    for i in range(n):
        o = 100 + 2 * i
        c = o + 1.6
        h = c + 0.1
        lo = o - 0.1
        bars.append((o, h, lo, c))
    return bars


def _falling(n=5):
    """Strictly decreasing bearish candles -> bearish last candle, no swings."""
    bars = []
    for i in range(n):
        o = 120 - 2 * i
        c = o - 1.6
        h = o + 0.1
        lo = c - 0.1
        bars.append((o, h, lo, c))
    return bars


# --------------------------------------------------------------------------- #
# Style configs
# --------------------------------------------------------------------------- #


def test_style_configs():
    fp = style_config(TraderStyle.FILTERING_PROCESS)
    assert isinstance(fp, StyleConfig)
    assert fp.multi_instrument is True
    assert fp.context_timeframe is Timeframe.H4
    assert fp.drill_floor is Timeframe.H4
    assert fp.requires_htf_context_before_drill is True

    fl = style_config(TraderStyle.FLOW)
    assert fl.multi_instrument is False
    assert fl.context_timeframe is Timeframe.M15
    assert fl.requires_htf_context_before_drill is False
    assert fl.guide_timeframes  # flow trader has FVG guide timeframes


# --------------------------------------------------------------------------- #
# Bias accumulation
# --------------------------------------------------------------------------- #


def test_bias_bullish(make_ohlc):
    bias = compute_bias({Timeframe.D1: make_ohlc(_rising())})
    assert isinstance(bias, Bias)
    assert bias.direction is Direction.BULLISH
    assert bias.n_bullish >= 1
    assert bias.n_bearish == 0
    assert bias.score >= 1


def test_bias_bearish(make_ohlc):
    bias = compute_bias({Timeframe.D1: make_ohlc(_falling())})
    assert bias.direction is Direction.BEARISH
    assert bias.n_bearish >= 1


def test_bias_one_sided_high_probability(make_ohlc):
    # Two bullish timeframes -> >=2 bullish args, none bearish -> one-sided.
    data = {Timeframe.D1: make_ohlc(_rising()), Timeframe.H4: make_ohlc(_rising())}
    bias = compute_bias(data)
    assert bias.direction is Direction.BULLISH
    assert bias.one_sided is True
    assert bias.n_bearish == 0
    assert bias.confidence == 1.0
    # invariant: one-sided implies no opposing arguments
    assert not (bias.one_sided and bias.n_bearish > 0)


# --------------------------------------------------------------------------- #
# Filtering process / ranking
# --------------------------------------------------------------------------- #


def test_filter_pairs_ranks_stronger_first(make_ohlc):
    strong = {Timeframe.D1: make_ohlc(_rising()), Timeframe.H4: make_ohlc(_rising())}
    weak = {Timeframe.D1: make_ohlc(_rising())}
    data_by_symbol = {"STRONG": strong, "WEAK": weak}

    ranked = filter_pairs(
        ["WEAK", "STRONG"], data_by_symbol=data_by_symbol, bars=None
    )
    assert [rp.symbol for rp in ranked][0] == "STRONG"
    # scores are non-increasing
    scores = [rp.rank_score for rp in ranked]
    assert scores == sorted(scores, reverse=True)

    bp = best_pair(["WEAK", "STRONG"], data_by_symbol=data_by_symbol, bars=None)
    assert bp is not None and bp.symbol == "STRONG"


def test_best_pair_empty():
    assert best_pair([], data_by_symbol={}) is None


# --------------------------------------------------------------------------- #
# Full top-down
# --------------------------------------------------------------------------- #


def test_top_down_result(make_ohlc):
    data = {Timeframe.D1: make_ohlc(_rising()), Timeframe.H4: make_ohlc(_rising())}
    res = top_down(data, style=TraderStyle.FILTERING_PROCESS)
    assert res.direction is Direction.BULLISH
    assert isinstance(res.narrative, str) and res.narrative
    assert res.probability == res.bias.confidence
    assert rank_score(res) >= res.bias.confidence

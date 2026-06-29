"""Unit tests for the timing layer (transcript 09 — Time Trading)."""

from __future__ import annotations

from datetime import date, time

import pandas as pd
import pytest

from mmc.timing import (
    BigThree,
    Impact,
    KillZone,
    NewsEvent,
    above_average_hours,
    affects_symbol,
    big_three_events,
    day_before_big_three_is_quiet,
    in_killzone,
    is_big_three,
    is_volatile_hour,
    killzone_window,
    real_volatility_day,
    real_volatility_event,
    true_range,
    volatility_by_hour,
    weekly_profile,
)


# --------------------------------------------------------------------------- #
# Sessions / kill zones
# --------------------------------------------------------------------------- #
class TestKillZones:
    def test_windows(self):
        assert killzone_window("forex") == (time(2, 0), time(10, 0))
        assert killzone_window("index") == (time(9, 30), time(16, 0))

    def test_forex_inside_and_outside(self):
        assert in_killzone(pd.Timestamp("2024-01-02 05:00"), "forex")
        assert not in_killzone(pd.Timestamp("2024-01-02 01:59"), "forex")
        assert not in_killzone(pd.Timestamp("2024-01-02 12:00"), "forex")

    def test_half_open_boundaries(self):
        # start is inclusive, end is exclusive
        assert in_killzone(pd.Timestamp("2024-01-02 02:00"), "forex")
        assert not in_killzone(pd.Timestamp("2024-01-02 10:00"), "forex")

    def test_index_window(self):
        assert not in_killzone(pd.Timestamp("2024-01-02 09:00"), "index")
        assert in_killzone(pd.Timestamp("2024-01-02 09:30"), "index")
        assert in_killzone(pd.Timestamp("2024-01-02 15:59"), "index")
        assert not in_killzone(pd.Timestamp("2024-01-02 16:00"), "index")

    def test_enum_accepted(self):
        assert in_killzone(pd.Timestamp("2024-01-02 03:00"), KillZone.FOREX)

    def test_naive_assumed_newyork(self):
        # naive 05:00 is treated as NY local -> inside forex zone
        assert in_killzone(pd.Timestamp("2024-01-02 05:00"), "forex")

    def test_aware_utc_is_converted(self):
        # 12:00 UTC == 07:00 New York (EST, UTC-5) -> inside forex zone.
        ts = pd.Timestamp("2024-01-02 12:00", tz="UTC")
        assert in_killzone(ts, "forex")
        # 09:00 UTC == 04:00 NY -> inside; but as a naive NY clock 09:00 is also
        # inside. Use 15:00 UTC == 10:00 NY -> exactly the exclusive end.
        assert not in_killzone(pd.Timestamp("2024-01-02 15:00", tz="UTC"), "forex")


# --------------------------------------------------------------------------- #
# Volatility profile from data
# --------------------------------------------------------------------------- #
class TestVolatilityByHour:
    def _df(self):
        # Two bars at hour 8 (range 4 and 6 -> avg 5), one at hour 9 (range 1),
        # one at hour 10 (range 1). Mean line = (5 + 1 + 1) / 3 = 2.33.
        idx = pd.DatetimeIndex(
            [
                "2024-01-01 08:00",
                "2024-01-01 08:30",
                "2024-01-01 09:00",
                "2024-01-01 10:00",
            ]
        )
        data = {
            "open": [10, 10, 10, 10],
            "high": [12, 13, 10.5, 10.5],
            "low": [8, 7, 9.5, 9.5],
            "close": [11, 11, 10, 10],
            "volume": [1, 1, 1, 1],
        }
        return pd.DataFrame(data, index=idx)

    def test_average_range_per_hour(self):
        profile = volatility_by_hour(self._df())
        assert profile.loc[8] == pytest.approx(5.0)  # (4 + 6) / 2
        assert profile.loc[9] == pytest.approx(1.0)
        assert profile.loc[10] == pytest.approx(1.0)
        assert list(profile.index) == [8, 9, 10]  # sorted, missing hours absent

    def test_above_average_flags(self):
        profile = volatility_by_hour(self._df())
        mask = above_average_hours(profile)
        # mean line ~2.33: only hour 8 is above it
        assert mask.loc[8]
        assert not mask.loc[9]
        assert not mask.loc[10]

    def test_is_volatile_hour(self):
        profile = volatility_by_hour(self._df())
        assert is_volatile_hour(8, profile)
        assert not is_volatile_hour(9, profile)
        assert not is_volatile_hour(3, profile)  # absent hour -> False

    def test_true_range_option(self):
        # smoke test that the true-range path runs and returns per-hour averages
        profile = volatility_by_hour(self._df(), use_true_range=True)
        assert set(profile.index) == {8, 9, 10}

    def test_true_range_values(self):
        df = self._df()
        tr = true_range(df)
        # first bar has no prev close -> plain H-L = 4
        assert tr.iloc[0] == pytest.approx(4.0)

    def test_requires_datetime_index(self):
        df = pd.DataFrame({"high": [1.0], "low": [0.0], "close": [0.5]})
        with pytest.raises(TypeError):
            volatility_by_hour(df)


# --------------------------------------------------------------------------- #
# News-event model
# --------------------------------------------------------------------------- #
def _nfp(ts="2024-01-05 08:30"):
    return NewsEvent("USD", "Non-Farm Employment Change", ts)


def _fomc(ts="2024-01-03 14:00"):
    return NewsEvent("USD", "FOMC Statement", ts)


def _cpi(ts="2024-01-11 08:30"):
    return NewsEvent("USD", "CPI m/m", ts)


class TestBigThree:
    def test_nfp_is_big_three(self):
        assert is_big_three(_nfp())
        assert is_big_three(_fomc())
        assert is_big_three(_cpi())

    def test_fomc_minutes_not_statement(self):
        # FOMC *minutes* (~16:43: "FOMC statement, not FOMC meeting") must not
        # match the big-three FOMC Statement.
        minutes = NewsEvent("USD", "FOMC Meeting Minutes", "2024-01-03 14:00")
        assert not is_big_three(minutes)

    def test_non_usd_not_big_three(self):
        aud_cpi = NewsEvent("AUD", "CPI q/q", "2024-01-04 00:30")
        assert not is_big_three(aud_cpi)

    def test_big_three_of_identity(self):
        from mmc.timing import big_three_of

        assert big_three_of(_nfp()) is BigThree.NFP
        assert big_three_of(_fomc()) is BigThree.FOMC_STATEMENT

    def test_default_impact_red(self):
        assert _nfp().is_red_folder
        assert _nfp().impact is Impact.RED


class TestWeeklyRules:
    def test_day_before_is_quiet(self):
        events = [_nfp("2024-01-05 08:30")]  # Friday
        assert day_before_big_three_is_quiet(date(2024, 1, 4), events)  # Thursday
        assert not day_before_big_three_is_quiet(date(2024, 1, 3), events)

    def test_last_big_three_brings_real_move(self):
        # FOMC Wednesday + NFP Friday in one week -> NFP (last) is the real move
        events = [_fomc("2024-01-03 14:00"), _nfp("2024-01-05 08:30")]
        assert real_volatility_day(events) == date(2024, 1, 5)
        assert real_volatility_event(events).name == "Non-Farm Employment Change"

    def test_weekly_profile_summary(self):
        events = [
            _fomc("2024-01-03 14:00"),
            _nfp("2024-01-05 08:30"),
            NewsEvent("AUD", "CPI q/q", "2024-01-04 00:30"),  # not USD big-three
        ]
        prof = weekly_profile(events)
        assert len(prof["big_three"]) == 2
        assert prof["real_volatility_day"] == date(2024, 1, 5)
        # quiet days = day before each big three (Jan 2 and Jan 4)
        assert date(2024, 1, 2) in prof["quiet_days"]
        assert date(2024, 1, 4) in prof["quiet_days"]

    def test_big_three_events_sorted(self):
        events = [_nfp("2024-01-05 08:30"), _fomc("2024-01-03 14:00")]
        bt = big_three_events(events)
        assert [e.name for e in bt] == ["FOMC Statement", "Non-Farm Employment Change"]


class TestAffectsSymbol:
    def test_aud_event(self):
        aud = NewsEvent("AUD", "CPI q/q", "2024-01-04 00:30")
        assert affects_symbol(aud, "AUDCHF")
        assert affects_symbol(aud, "AUDUSD")
        assert not affects_symbol(aud, "EURUSD")

    def test_usd_event_affects_gold(self):
        usd = _nfp()
        assert affects_symbol(usd, "EURUSD")
        assert affects_symbol(usd, "XAUUSD")  # gold priced in USD
        assert not affects_symbol(usd, "EURGBP")

    def test_case_insensitive(self):
        usd = _nfp()
        assert affects_symbol(usd, "eurusd")

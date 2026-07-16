"""Tests for the signal layer.

The project's central claim is that confidence-weighted reasoning over CAMARA
congestion data beats threshold logic. That claim lives in these functions, so
it gets tested. Payloads are the real ones recorded from the Nokia NaC portal
playground on 2026-07-15.

    python -m pytest tests/ -v
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sakina.signals import (  # noqa: E402
    CongestionRead,
    LocationRead,
    ReachabilityRead,
    parse_identity,
)

# Verbatim from the portal playground.
PLAYGROUND_CONGESTION = [
    {"timeIntervalStart": "2026-07-15T13:48:45.502075Z", "timeIntervalStop": "2026-07-15T13:53:45.502075Z", "congestionLevel": "Low", "confidenceLevel": 97},
    {"timeIntervalStart": "2026-07-15T13:43:45.502075Z", "timeIntervalStop": "2026-07-15T13:48:45.502075Z", "congestionLevel": "High", "confidenceLevel": 51},
    {"timeIntervalStart": "2026-07-15T13:38:45.502075Z", "timeIntervalStop": "2026-07-15T13:43:45.502075Z", "congestionLevel": "Medium", "confidenceLevel": 16},
    {"timeIntervalStart": "2026-07-15T13:33:45.502075Z", "timeIntervalStop": "2026-07-15T13:38:45.502075Z", "congestionLevel": "High", "confidenceLevel": 71},
]


class TestCongestionOrdering:
    def test_api_returns_newest_first_we_sort_oldest_first(self):
        """The API hands back reverse-chronological. Trend math needs the opposite.

        Getting this backwards inverts every trend conclusion the agent draws,
        silently. Hence the test.
        """
        c = CongestionRead.parse(PLAYGROUND_CONGESTION)
        assert [b.level for b in c.buckets] == ["High", "Medium", "High", "Low"]
        assert [b.confidence for b in c.buckets] == [71, 16, 51, 97]

    def test_latest_is_the_most_recent_bucket(self):
        c = CongestionRead.parse(PLAYGROUND_CONGESTION)
        assert c.latest.level == "Low"
        assert c.latest.confidence == 97


class TestConfidenceWeighting:
    """The core claim, tested."""

    def test_weighted_mean_differs_from_naive(self):
        c = CongestionRead.parse(PLAYGROUND_CONGESTION)
        # naive: (2 + 1 + 2 + 0) / 4 = 1.25
        assert round(c.naive_mean, 2) == 1.25
        # weighted: (2*71 + 1*16 + 2*51 + 0*97) / (71+16+51+97) = 260/235
        assert round(c.weighted_mean, 3) == 1.106
        assert c.weighted_mean < c.naive_mean

    def test_low_confidence_reading_is_discounted(self):
        """The Medium@16% should barely move the mean."""
        with_noise = CongestionRead.parse(PLAYGROUND_CONGESTION)
        without = CongestionRead.parse(
            [b for b in PLAYGROUND_CONGESTION if b["confidenceLevel"] != 16]
        )
        assert abs(with_noise.weighted_mean - without.weighted_mean) < 0.06

    def test_trust_floor_flags_the_noise(self):
        c = CongestionRead.parse(PLAYGROUND_CONGESTION)
        assert len(c.trusted_only) == 3
        assert [b for b in c.buckets if not b.trustworthy][0].confidence == 16

    def test_confident_high_outweighs_uncertain_low(self):
        """A trustworthy High must not be washed out by a doubtful Low."""
        c = CongestionRead.parse([
            {"timeIntervalStart": "2026-07-15T13:00:00Z", "congestionLevel": "High", "confidenceLevel": 95},
            {"timeIntervalStart": "2026-07-15T13:05:00Z", "congestionLevel": "Low", "confidenceLevel": 10},
        ])
        assert c.weighted_mean > 1.5  # still reads as High-ish
        assert c.naive_mean == 1.0  # naive says "Medium" — wrong


class TestDispersalVsBlindness:
    """The distinction the whole agent exists to make."""

    def test_improving_confidence_supports_real_dispersal(self):
        c = CongestionRead.parse(PLAYGROUND_CONGESTION)
        assert c.confidence_trend == "improving"  # 71 -> 97

    def test_degrading_confidence_means_we_are_going_blind(self):
        c = CongestionRead.parse([
            {"timeIntervalStart": "2026-07-15T13:00:00Z", "congestionLevel": "High", "confidenceLevel": 95},
            {"timeIntervalStart": "2026-07-15T13:05:00Z", "congestionLevel": "Low", "confidenceLevel": 20},
        ])
        assert c.confidence_trend == "degrading"
        # Same apparent "congestion fell" as above, opposite meaning.

    def test_volatility_detects_unsettled_cell(self):
        c = CongestionRead.parse(PLAYGROUND_CONGESTION)
        assert round(c.volatility, 2) == 1.33  # High->Med->High->Low

        steady = CongestionRead.parse([
            {"timeIntervalStart": "2026-07-15T13:00:00Z", "congestionLevel": "Low", "confidenceLevel": 90},
            {"timeIntervalStart": "2026-07-15T13:05:00Z", "congestionLevel": "Low", "confidenceLevel": 92},
        ])
        assert steady.volatility == 0.0


class TestEmptyAndMalformed:
    def test_empty_does_not_divide_by_zero(self):
        c = CongestionRead.parse([])
        assert c.weighted_mean == 0.0
        assert c.naive_mean == 0.0
        assert c.volatility == 0.0
        assert c.latest is None
        assert c.confidence_trend == "unknown"

    def test_zero_confidence_everywhere_does_not_crash(self):
        c = CongestionRead.parse([
            {"timeIntervalStart": "2026-07-15T13:00:00Z", "congestionLevel": "High", "confidenceLevel": 0},
        ])
        assert c.weighted_mean == 0.0  # no evidence weight at all

    def test_snake_case_from_sdk_also_parses(self):
        """Wire is camelCase; the Fern SDK may hand back snake_case."""
        c = CongestionRead.parse([
            {"time_interval_start": "2026-07-15T13:00:00Z", "congestion_level": "High", "confidence_level": 80},
        ])
        assert c.latest.level == "High"
        assert c.latest.confidence == 80


class TestLocation:
    def test_playground_fix_is_coarse(self):
        loc = LocationRead.parse({
            "lastLocationTime": "2026-07-15T13:45:52.422447Z",
            "area": {"areaType": "CIRCLE", "center": {"latitude": 47.486, "longitude": 19.079}, "radius": 1000},
        })
        assert loc.precision_note == "coarse fix"
        assert loc.radius_m == 1000

    def test_old_fix_is_stale(self):
        old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        loc = LocationRead.parse({"lastLocationTime": old, "area": {"center": {"latitude": 1, "longitude": 1}, "radius": 100}})
        assert loc.stale

    def test_fresh_fix_is_not_stale(self):
        now = datetime.now(timezone.utc).isoformat()
        loc = LocationRead.parse({"lastLocationTime": now, "area": {"center": {"latitude": 1, "longitude": 1}, "radius": 100}})
        assert not loc.stale


class TestReachability:
    def test_sms_only_is_detected(self):
        r = ReachabilityRead.parse({"reachable": True, "connectivity": ["SMS"]})
        assert r.sms_only
        assert not r.data_capable

    def test_data_capable_is_not_sms_only(self):
        r = ReachabilityRead.parse({"reachable": True, "connectivity": ["DATA", "SMS"]})
        assert not r.sms_only
        assert r.data_capable

    def test_unreachable_is_not_sms_only(self):
        r = ReachabilityRead.parse({"reachable": False, "connectivity": []})
        assert not r.sms_only


class TestIdentity:
    def test_compromised_responder_raises_three_concerns(self):
        """+99999991000 as the simulator actually returns it."""
        i = parse_identity(
            {"swapped": True},
            {"latestSimChange": datetime.now(timezone.utc).isoformat()},
            {"roaming": True, "countryName": ["HU"]},
            {"verificationResult": "FALSE"},
        )
        assert len(i.concerns) == 3
        assert not i.clean
        assert i.country == "HU"
        assert i.swap_age_h < 1

    def test_clean_responder_has_no_concerns(self):
        i = parse_identity(
            {"swapped": False},
            {"latestSimChange": "2025-11-02T08:14:22Z"},
            {"roaming": False, "countryName": ["SA"]},
            {"verificationResult": "TRUE"},
        )
        assert i.clean
        assert i.concerns == []

    def test_roaming_alone_is_one_concern_not_a_verdict(self):
        """Hajj is the largest roaming event on earth. Roaming != fraud."""
        i = parse_identity(
            {"swapped": False},
            {"latestSimChange": "2025-01-01T00:00:00Z"},
            {"roaming": True, "countryName": ["EG"]},
            {"verificationResult": "TRUE"},
        )
        assert len(i.concerns) == 1
        assert "roaming" in i.concerns[0]

"""Tests for multi-zone scheduling (S3.1).

The claim under test: the agent picks which zone to look at next by itself,
using deterministic priority arithmetic — never-polled zones first (ties
broken by criticality), then overdue-ness scaled by last risk and
criticality. No LLM involved; this is signals.py-style arithmetic, so it is
tested the same way.

    python -m pytest tests/ -v
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sakina import config  # noqa: E402
from sakina.scheduler import ZoneStatus, explain, pick_next_zone  # noqa: E402

NOW = datetime(2026, 7, 17, 12, 0, 0, tzinfo=timezone.utc)


def fresh_statuses() -> dict[str, ZoneStatus]:
    return {z.id: ZoneStatus(zone_id=z.id) for z in config.ZONES}


class TestNeverPolled:
    def test_never_polled_zones_outrank_everything(self):
        statuses = fresh_statuses()
        # Give one zone a recent, high-risk, highly-overdue-looking reading —
        # it still must lose to any zone that has never been read at all.
        statuses["mina-camps-a"] = ZoneStatus(
            zone_id="mina-camps-a",
            last_risk=0.95,
            last_polled=NOW - timedelta(hours=5),
            next_poll_s=30,
        )
        chosen = pick_next_zone(statuses, now=NOW)
        assert statuses[chosen].last_polled is None

    def test_ties_among_never_polled_broken_by_criticality(self):
        statuses = fresh_statuses()
        chosen = pick_next_zone(statuses, now=NOW)
        top_criticality = max(z.criticality for z in config.ZONES)
        assert config.ZONES_BY_ID[chosen].criticality == top_criticality


class TestOverdueScaling:
    def test_more_overdue_and_riskier_zone_wins(self):
        statuses = {
            "jamarat-bridge": ZoneStatus(
                zone_id="jamarat-bridge",
                last_risk=0.75,
                last_polled=NOW - timedelta(seconds=120),
                next_poll_s=30,  # 4x overdue
            ),
            "street-204": ZoneStatus(
                zone_id="street-204",
                last_risk=0.20,
                last_polled=NOW - timedelta(seconds=40),
                next_poll_s=30,  # barely overdue
            ),
        }
        assert pick_next_zone(statuses, now=NOW) == "jamarat-bridge"

    def test_lower_criticality_zone_can_still_lose_even_if_more_overdue(self, monkeypatch):
        from sakina import scheduler
        monkeypatch.setattr(scheduler, "observable", lambda zid: True)
        # tunnel-al-muaisim (criticality 4) very overdue but low risk vs.
        # jamarat-bridge (criticality 5) moderately overdue and high risk.
        statuses = {
            "tunnel-al-muaisim": ZoneStatus(
                zone_id="tunnel-al-muaisim",
                last_risk=0.10,
                last_polled=NOW - timedelta(seconds=600),
                next_poll_s=60,  # 10x overdue, but low risk
            ),
            "jamarat-bridge": ZoneStatus(
                zone_id="jamarat-bridge",
                last_risk=0.90,
                last_polled=NOW - timedelta(seconds=300),
                next_poll_s=60,  # 5x overdue, high risk
            ),
        }
        # 10 * (0.5+0.05) * (4/5) = 4.4   vs   5 * (0.5+0.45) * (5/5) = 4.75
        assert pick_next_zone(statuses, now=NOW) == "jamarat-bridge"


class TestExplain:
    def test_explains_never_polled(self):
        statuses = fresh_statuses()
        chosen = pick_next_zone(statuses, now=NOW)
        text = explain(statuses, chosen, now=NOW)
        assert "never polled" in text

    def test_explains_polled_zone_with_numbers(self):
        statuses = {
            "jamarat-bridge": ZoneStatus(
                zone_id="jamarat-bridge",
                last_risk=0.42,
                last_polled=NOW - timedelta(seconds=90),
                next_poll_s=60,
            ),
        }
        text = explain(statuses, "jamarat-bridge", now=NOW)
        assert "90s" in text
        assert "0.42" in text
        assert "criticality 5/5" in text


class TestEmpty:
    def test_raises_on_empty_statuses(self):
        import pytest

        with pytest.raises(ValueError):
            pick_next_zone({})


class TestObservability:
    def test_never_picks_a_zone_with_no_devices(self):
        statuses = fresh_statuses()
        for _ in range(6):
            chosen = pick_next_zone(statuses, now=NOW)
            assert config.devices_in_zone(chosen), f"picked unobservable zone {chosen}"
            statuses[chosen] = ZoneStatus(zone_id=chosen, last_risk=0.2, last_polled=NOW, next_poll_s=60)

    def test_unobservable_zones_are_skipped_even_when_never_polled(self):
        statuses = fresh_statuses()
        for zid in ("jamarat-bridge", "street-204"):
            statuses[zid] = ZoneStatus(zone_id=zid, last_risk=0.1, last_polled=NOW, next_poll_s=60)
        assert pick_next_zone(statuses, now=NOW) in ("jamarat-bridge", "street-204")

    def test_all_unobservable_raises(self):
        import pytest
        statuses = {z: ZoneStatus(zone_id=z) for z in ("mina-camps-a", "tunnel-al-muaisim")}
        with pytest.raises(ValueError, match="observable"):
            pick_next_zone(statuses, now=NOW)

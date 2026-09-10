"""S3.5: network-failure behavior of CamaraTools._invoke.

Simulates a live call raising (e.g. a network timeout) and checks the two
documented, opposite-on-purpose behaviors: hybrid mode must degrade to a
recorded fixture and keep going; live mode must never mask the failure by
serving stale data — it must raise. Uses a fake client so no real network
call happens; the recorded fixture for +99999991002 already exists on disk
from S1.1.

    python -m pytest tests/ -v
"""
from __future__ import annotations

import pytest

from sakina import config
from sakina.camara import CamaraTools
from sakina.trace import EventKind, Source, Trace

PROBE = config.DEVICES_BY_NUMBER["+99999991002"]  # has a recorded congestion_ fixture


class _RaisingCongestionClient:
    def query(self, **kwargs):
        raise TimeoutError("simulated network timeout")


class _RaisingClient:
    def __init__(self):
        self.congestion_insights = _RaisingCongestionClient()


def test_hybrid_mode_degrades_to_fixture_on_network_failure():
    trace = Trace()
    tools = CamaraTools(trace=trace, mode="hybrid")
    tools._client = _RaisingClient()  # force the live path to fail

    data = tools.congestion(PROBE)  # must not raise

    assert data  # the recorded fixture, not an empty/None result
    assert any(e.kind is EventKind.DEGRADE for e in trace.events)
    cache_calls = [e for e in trace.api_calls() if e.source is Source.CACHE]
    assert cache_calls, "expected the fallback call to be logged as CACHE provenance"


def test_live_mode_raises_instead_of_masking_failure():
    trace = Trace()
    tools = CamaraTools(trace=trace, mode="live")
    tools._client = _RaisingClient()

    with pytest.raises(TimeoutError):
        tools.congestion(PROBE)

    assert any(e.kind is EventKind.ERROR for e in trace.events)

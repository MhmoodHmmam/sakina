"""S3.5: the whole agent cycle must survive a malformed model response.

Unit tests in test_brain.py check assess_zone()/gate_responders() in
isolation. This checks the wiring: agent.py's _assess()/_decide() only catch
brain.LLMUnavailable, so a full cycle must not crash end-to-end when the
model returns syntactically valid but semantically malformed JSON — it must
fall through to the heuristic / fail-closed paths and finish with a REPORT,
using recorded fixtures so no network or API key is needed.

    python -m pytest tests/ -v
"""
from __future__ import annotations

from sakina import brain
from sakina.agent import Sakina
from sakina.camara import CamaraTools
from sakina.trace import EventKind


def test_full_cycle_survives_malformed_model_output(monkeypatch):
    monkeypatch.setattr(brain, "reason", lambda *a, **k: {
        "risk_score": "very high",  # wrong type — the exact real-world failure mode
        "confidence": "medium",
    })

    agent = Sakina(CamaraTools(mode="replay"))
    state, trace = agent.cycle("jamarat-bridge")

    # Must reach REPORT — i.e. must not raise out of graph.invoke().
    assert "assessment" in state
    # Heuristic fallback must have taken over, and it must say so in the trace.
    assert state["assessment"]["model"] == "heuristic"
    assert any(e.kind is EventKind.DEGRADE for e in trace.events)


def test_zone_with_no_devices_raises_clear_error_not_index_error():
    import pytest
    agent = Sakina(CamaraTools(mode="replay"))
    with pytest.raises(ValueError, match="no assigned devices"):
        agent.cycle("tunnel-al-muaisim")

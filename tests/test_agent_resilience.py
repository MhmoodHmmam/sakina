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

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sakina import brain  # noqa: E402
from sakina.agent import Sakina  # noqa: E402
from sakina.camara import CamaraTools  # noqa: E402
from sakina.trace import EventKind  # noqa: E402


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

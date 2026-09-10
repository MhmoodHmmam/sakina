"""Tests for the reasoning layer's shape validation (S3.5).

reason() already retries a JSON parse failure against the next provider.
These test the harder case: syntactically valid JSON with the wrong field
types or shape. That parses fine and, before this fix, crashed
assess_zone()/gate_responders() with an uncaught ValueError/AttributeError
instead of degrading to the same LLMUnavailable path a missing model already
takes. Confirmed as a real crash (not theoretical) before writing the fix.

    python -m pytest tests/ -v
"""
from __future__ import annotations

import pytest

from sakina import brain
from sakina.trace import EventKind, Trace


def test_assess_zone_raises_llm_unavailable_on_bad_types(monkeypatch):
    monkeypatch.setattr(brain, "reason", lambda *a, **k: {
        "risk_score": "high",  # wrong type — str, not float
        "confidence": "medium", "reading": "x", "reasoning": "y",
        "primary_driver": "z", "contradictions": [], "recommended_poll_s": 60,
        "escalate_identity_check": False, "_model": "gemini",
    })
    trace = Trace()
    with pytest.raises(brain.LLMUnavailable):
        brain.assess_zone("evidence", trace)
    assert any(e.kind is EventKind.DEGRADE for e in trace.events)


def test_gate_responders_raises_llm_unavailable_when_decisions_not_a_list(monkeypatch):
    monkeypatch.setattr(brain, "reason", lambda *a, **k: {
        "decisions": "not-a-list", "summary": "x",
    })
    trace = Trace()
    with pytest.raises(brain.LLMUnavailable):
        brain.gate_responders("evidence", trace)
    assert any(e.kind is EventKind.DEGRADE for e in trace.events)


def test_gate_responders_rejects_decisions_containing_non_dicts(monkeypatch):
    monkeypatch.setattr(brain, "reason", lambda *a, **k: {
        "decisions": ["not-a-dict", {"phone_number": "+1"}], "summary": "x",
    })
    trace = Trace()
    with pytest.raises(brain.LLMUnavailable):
        brain.gate_responders("evidence", trace)


def test_valid_assessment_shape_still_passes_through(monkeypatch):
    monkeypatch.setattr(brain, "reason", lambda *a, **k: {
        "risk_score": 0.5, "confidence": "high", "reading": "ok", "reasoning": "ok",
        "primary_driver": "x", "contradictions": [], "recommended_poll_s": 60,
        "escalate_identity_check": False, "_model": "gemini",
    })
    a = brain.assess_zone("evidence", Trace())
    assert a.risk_score == 0.5


def test_valid_verdict_shape_still_passes_through(monkeypatch):
    monkeypatch.setattr(brain, "reason", lambda *a, **k: {
        "decisions": [{"phone_number": "+1", "allow": True, "rationale": "ok", "severity": "clear"}],
        "summary": "fine",
    })
    verdict = brain.gate_responders("evidence", Trace())
    assert verdict["decisions"][0]["allow"] is True

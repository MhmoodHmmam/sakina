"""End-to-end check that agent.cycle(language="ar") actually produces an
Arabic trace, not just that i18n.py's lookup table is internally consistent.
Uses replay mode against the recorded fixtures and a stubbed model, so it is
hermetic: no network, no API keys, and no quota burned per test run. The
phase labels under test come from i18n.py, not from the model.

    python -m pytest tests/ -v
"""
from __future__ import annotations

import pytest

from sakina import brain
from sakina.agent import Sakina
from sakina.camara import CamaraTools
from sakina.trace import EventKind

# Risk above escalate_at so the cycle walks VERIFY -> DECIDE -> REPORT; an empty
# decisions list is a valid verdict that elevates nobody.
_CANNED_MODEL = {
    "risk_score": 0.72,
    "confidence": "medium",
    "reading": "stubbed",
    "escalate_identity_check": True,
    "decisions": [],
    "_model": "stub",
}


@pytest.fixture(autouse=True)
def stub_model(monkeypatch):
    monkeypatch.setattr(brain, "reason", lambda *a, **k: dict(_CANNED_MODEL))


def test_arabic_cycle_produces_arabic_phase_labels():
    agent = Sakina(CamaraTools(mode="replay"))
    state, trace = agent.cycle("jamarat-bridge", language="ar")

    phase_labels = [e.label for e in trace.events if e.kind is EventKind.PHASE]
    assert "الإدراك" in phase_labels  # PERCEIVE
    assert "التقييم" in phase_labels  # ASSESS
    # None of the English phase labels should appear in an Arabic cycle.
    assert "PERCEIVE" not in phase_labels
    assert "ASSESS" not in phase_labels


def test_english_cycle_unaffected_by_default():
    agent = Sakina(CamaraTools(mode="replay"))
    state, trace = agent.cycle("jamarat-bridge")  # language defaults to "en"

    phase_labels = [e.label for e in trace.events if e.kind is EventKind.PHASE]
    assert "PERCEIVE" in phase_labels
    assert "ASSESS" in phase_labels

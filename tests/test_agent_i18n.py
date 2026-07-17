"""End-to-end check that agent.cycle(language="ar") actually produces an
Arabic trace, not just that i18n.py's lookup table is internally consistent.
Uses replay mode against the recorded fixtures — no network, no API keys.

    python -m pytest tests/ -v
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sakina.agent import Sakina  # noqa: E402
from sakina.camara import CamaraTools  # noqa: E402
from sakina.trace import EventKind  # noqa: E402


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

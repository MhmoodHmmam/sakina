"""Tests for the localization lookup (i18n.py).

Deterministic string lookup, same spirit as signals.py: no judgement, just
presentation. The one real failure mode is a template whose Arabic and
English variants don't accept the same placeholders — caught here rather
than at demo time.

    python -m pytest tests/ -v
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sakina import i18n  # noqa: E402


def _placeholders(template: str) -> set[str]:
    return set(re.findall(r"\{(\w+)(?::[^}]*)?\}", template))


class TestTemplatesConsistent:
    def test_every_key_has_both_languages(self):
        for key, entry in i18n._STRINGS.items():
            assert "en" in entry, f"{key} missing en"
            assert "ar" in entry, f"{key} missing ar"

    def test_placeholders_match_between_languages(self):
        for key, entry in i18n._STRINGS.items():
            en_ph = _placeholders(entry["en"])
            ar_ph = _placeholders(entry["ar"])
            assert en_ph == ar_ph, f"{key}: en={en_ph} ar={ar_ph}"


class TestLookup:
    def test_falls_back_to_english_for_unknown_language(self):
        assert i18n.t("phase.perceive", "fr") == "PERCEIVE"

    def test_unknown_key_returns_the_key_itself_not_a_crash(self):
        assert i18n.t("no.such.key", "ar") == "no.such.key"

    def test_formats_with_kwargs(self):
        assert i18n.t("phase.perceive.detail", "en", zone="Jamarat Bridge") == (
            "Gathering network signals across Jamarat Bridge"
        )
        assert i18n.t("phase.perceive.detail", "ar", zone="جسر الجمرات") == (
            "جمع إشارات الشبكة عبر جسر الجمرات"
        )

    def test_arabic_lookup_differs_from_english(self):
        assert i18n.t("phase.assess", "ar") != i18n.t("phase.assess", "en")


class TestEnumLabels:
    def test_confidence_labels(self):
        assert i18n.confidence_label("high", "en") == "high"
        assert i18n.confidence_label("high", "ar") == "عالية"

    def test_severity_labels(self):
        assert i18n.severity_label("block", "ar") == "حظر"

    def test_trend_labels(self):
        assert i18n.trend_label("improving", "ar") == "في تحسّن"

    def test_verdict_labels(self):
        assert i18n.verdict_label(True, "en") == "ALLOW"
        assert i18n.verdict_label(True, "ar") == "سماح"
        assert i18n.verdict_label(False, "ar") == "رفض"

    def test_unknown_enum_value_falls_back_to_input(self):
        assert i18n.confidence_label("nonsense", "ar") == "nonsense"

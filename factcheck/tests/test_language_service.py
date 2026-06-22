"""Tests for the language detection service (Phase 2).

Covers the English/Bangla split plus the graceful-handling cases the pipeline
depends on: mixed-script text, empty input, and very short strings must never
raise (AGENT.md Rule 12).
"""

from django.test import SimpleTestCase

from factcheck.services.language_service import detect_language


class DetectLanguageTests(SimpleTestCase):
    """Behaviour of :func:`detect_language` across scripts and edge cases."""

    def test_detects_english(self):
        """A clear English sentence is detected as ``"en"``."""
        self.assertEqual(detect_language("The Earth orbits the Sun every year."), "en")

    def test_detects_bangla(self):
        """A clear Bangla sentence is detected as ``"bn"``."""
        self.assertEqual(detect_language("ঢাকা বাংলাদেশের রাজধানী।"), "bn")

    def test_bengali_dominant_mixed_text_is_bangla(self):
        """Mixed script that is mostly Bengali resolves to ``"bn"`` without error."""
        self.assertEqual(detect_language("বাংলা text mixed এখানে"), "bn")

    def test_empty_string_is_unknown(self):
        """Empty and whitespace-only input returns ``"unknown"`` rather than raising."""
        self.assertEqual(detect_language(""), "unknown")
        self.assertEqual(detect_language("   "), "unknown")

    def test_non_alpha_input_is_unknown(self):
        """Digits/punctuation only (no letters) returns ``"unknown"``."""
        self.assertEqual(detect_language("12345 !!! ---"), "unknown")

    def test_short_latin_string_does_not_raise(self):
        """A very short Latin string is handled gracefully (treated as English)."""
        self.assertEqual(detect_language("Hi"), "en")

    def test_short_bangla_string(self):
        """A short Bengali-script string is detected as ``"bn"``."""
        self.assertEqual(detect_language("ঢাকা"), "bn")

    def test_other_script_is_unknown(self):
        """Text in a non-Latin, non-Bengali script (e.g. Cyrillic, CJK) is unknown."""
        self.assertEqual(detect_language("Привет мир, как дела"), "unknown")
        self.assertEqual(detect_language("你好世界"), "unknown")

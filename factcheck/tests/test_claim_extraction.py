"""Tests for the claim extraction service (Phase 2).

English cases exercise the spaCy Pass 1 dependency parse. Bangla cases run with
the transformer fallback disabled (``ENABLE_HF_FALLBACK=False``) so they hit the
deterministic heuristic fallback — keeping the suite fast and offline. The real
HuggingFace zero-shot path is validated manually rather than in CI.

These tests assert the public contract only (:func:`extract_claims`); internal
helpers are never called directly (AGENT.md Rule 13).
"""

from django.test import SimpleTestCase, override_settings

from factcheck.services.claim_extraction import extract_claims


class ExtractClaimsEnglishTests(SimpleTestCase):
    """spaCy-backed extraction of English factual claims."""

    def _assert_claim_shape(self, claim):
        """Every returned claim has the locked ``{claim, confidence, lang}`` shape."""
        self.assertEqual(set(claim), {"claim", "confidence", "lang"})
        self.assertIsInstance(claim["claim"], str)
        self.assertIsInstance(claim["confidence"], float)
        self.assertIn(claim["lang"], {"en", "bn"})

    def test_simple_factual_claim(self):
        """A simple factual sentence yields exactly one English claim."""
        claims = extract_claims("The Earth orbits the Sun.")
        self.assertEqual(len(claims), 1)
        self._assert_claim_shape(claims[0])
        self.assertEqual(claims[0]["lang"], "en")
        self.assertIn("orbits", claims[0]["claim"].lower())
        self.assertGreaterEqual(claims[0]["confidence"], 0.5)

    def test_compound_sentence_yields_multiple_claims(self):
        """A coordinated compound sentence splits into separate claims."""
        claims = extract_claims("Marie Curie won two Nobel Prizes and she discovered radium.")
        self.assertGreaterEqual(len(claims), 2)
        joined = " ".join(c["claim"].lower() for c in claims)
        self.assertIn("nobel", joined)
        self.assertIn("radium", joined)

    def test_multiple_sentences_yield_multiple_claims(self):
        """Each factual sentence in a paragraph becomes its own claim."""
        text = "Water boils at 100 degrees Celsius. The Pacific is the largest ocean."
        claims = extract_claims(text)
        self.assertEqual(len(claims), 2)
        for claim in claims:
            self._assert_claim_shape(claim)

    def test_opinion_text_yields_no_confident_claims(self):
        """Opinion/subjective text produces no claims above the threshold."""
        claims = extract_claims("I think pizza is the best food and I really love it.")
        self.assertEqual(claims, [])

    def test_question_yields_no_claims(self):
        """A question is not a factual assertion and yields nothing."""
        self.assertEqual(extract_claims("Is the Earth really flat?"), [])

    def test_html_input_is_sanitized(self):
        """HTML tags and scripts are stripped; the clean claim survives."""
        text = "<p>The <b>Nile</b> is a river.</p><script>alert('x')</script>"
        claims = extract_claims(text)
        self.assertEqual(len(claims), 1)
        self.assertNotIn("<", claims[0]["claim"])
        self.assertNotIn("alert", claims[0]["claim"].lower())
        self.assertIn("nile", claims[0]["claim"].lower())

    def test_empty_string_returns_empty_list(self):
        """Empty / whitespace / unsupported input returns ``[]`` without raising."""
        self.assertEqual(extract_claims(""), [])
        self.assertEqual(extract_claims("   "), [])
        self.assertEqual(extract_claims("<div></div>"), [])


@override_settings(ENABLE_HF_FALLBACK=False)
class ExtractClaimsBanglaTests(SimpleTestCase):
    """Bangla routing through the fallback pass (heuristic mode for speed)."""

    def test_bangla_factual_sentence(self):
        """A Bangla factual sentence yields a claim tagged ``"bn"``."""
        claims = extract_claims("ঢাকা বাংলাদেশের রাজধানী।")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["lang"], "bn")
        self.assertIn("ঢাকা", claims[0]["claim"])

    def test_bangla_multiple_sentences(self):
        """Multiple Bangla sentences each become a claim."""
        text = "সূর্য পূর্ব দিকে ওঠে। পানি একশ ডিগ্রি সেলসিয়াসে ফোটে।"
        claims = extract_claims(text)
        self.assertEqual(len(claims), 2)
        for claim in claims:
            self.assertEqual(claim["lang"], "bn")
            self.assertEqual(set(claim), {"claim", "confidence", "lang"})

    def test_bangla_question_is_skipped(self):
        """A Bangla question (ending in '?') is not returned as a claim."""
        self.assertEqual(extract_claims("তুমি কেমন আছ?"), [])


class ConfidenceThresholdTests(SimpleTestCase):
    """The confidence threshold is read from settings, never hardcoded."""

    @override_settings(CLAIM_CONFIDENCE_THRESHOLD=0.99)
    def test_high_threshold_filters_everything(self):
        """Raising the threshold to near-1.0 filters out ordinary claims."""
        self.assertEqual(extract_claims("The Earth orbits the Sun."), [])

    @override_settings(CLAIM_CONFIDENCE_THRESHOLD=0.0)
    def test_zero_threshold_keeps_claims(self):
        """A zero threshold keeps the extracted claim."""
        self.assertTrue(extract_claims("The Earth orbits the Sun."))

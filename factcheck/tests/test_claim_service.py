"""Tests for the claim orchestration service (Phase 2).

Verifies that :func:`process_text_input` persists extracted claims to the
``Claim`` model with the expected fields populated. Database writes belong here,
not in the extraction stage (AGENT.md Rule 13).
"""

from django.test import TestCase

from factcheck.models import Claim
from factcheck.services import claim_service


class ProcessTextInputTests(TestCase):
    """Persistence behaviour of :func:`claim_service.process_text_input`."""

    def test_creates_claim_rows(self):
        """Each extracted claim is saved as a ``Claim`` row with fields populated."""
        text = "The Earth orbits the Sun. The Moon orbits the Earth."
        saved = claim_service.process_text_input(text, "text")

        self.assertGreaterEqual(len(saved), 2)
        self.assertEqual(Claim.objects.count(), len(saved))

        claim = saved[0]
        self.assertEqual(claim.raw_text, text)
        self.assertTrue(claim.extracted_claim)
        self.assertEqual(claim.language, "en")
        self.assertEqual(claim.source_input_type, "text")
        self.assertIsNotNone(claim.created_at)

    def test_no_claims_writes_nothing(self):
        """Input with no confident claims persists no rows and returns ``[]``."""
        saved = claim_service.process_text_input("Is the sky blue?", "text")
        self.assertEqual(saved, [])
        self.assertEqual(Claim.objects.count(), 0)

    def test_invalid_source_type_raises(self):
        """An unsupported ``source_type`` raises ``ValueError`` before any write."""
        with self.assertRaises(ValueError):
            claim_service.process_text_input("The Earth orbits the Sun.", "audio")
        self.assertEqual(Claim.objects.count(), 0)

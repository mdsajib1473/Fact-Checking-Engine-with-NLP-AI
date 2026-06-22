"""Tests for the POST /api/v1/extract/ development endpoint (Phase 2).

Confirms the success-response shape and the input-validation rejections
(AGENT.md Rule 6). This endpoint is a testing harness for the NLP pipeline, not
the final UI flow (which arrives in Phase 4).
"""

from django.test import TestCase
from django.urls import reverse

from factcheck.models import Claim


class ExtractApiTests(TestCase):
    """Request/response contract of the claim-extraction endpoint."""

    def setUp(self):
        """Resolve the endpoint URL once for all tests."""
        self.url = reverse("factcheck:extract")

    def test_valid_request_returns_200_with_shape(self):
        """A valid English paragraph returns 200 with claims/language/count."""
        text = "The Earth orbits the Sun. Water boils at 100 degrees Celsius."
        response = self.client.post(
            self.url, data={"text": text, "source_type": "text"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual(set(body), {"claims", "language", "count"})
        self.assertEqual(body["language"], "en")
        self.assertEqual(body["count"], len(body["claims"]))
        self.assertGreaterEqual(body["count"], 2)
        self.assertEqual(Claim.objects.count(), body["count"])

    def test_source_type_defaults_to_text(self):
        """``source_type`` is optional and defaults to ``"text"``."""
        response = self.client.post(
            self.url, data={"text": "The Earth orbits the Sun."}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)

    def test_empty_text_returns_400(self):
        """Empty text fails validation with 400."""
        response = self.client.post(
            self.url, data={"text": "", "source_type": "text"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Claim.objects.count(), 0)

    def test_too_short_text_returns_400(self):
        """Text below the minimum length fails validation with 400."""
        response = self.client.post(
            self.url, data={"text": "short", "source_type": "text"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

    def test_oversized_text_returns_400(self):
        """Text above the maximum length fails validation with 400."""
        response = self.client.post(
            self.url,
            data={"text": "a" * 5001, "source_type": "text"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Claim.objects.count(), 0)

    def test_missing_text_returns_400(self):
        """A request body with no ``text`` field fails validation with 400."""
        response = self.client.post(
            self.url, data={"source_type": "text"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)

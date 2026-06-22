"""DRF serializers for the fact-checking app.

Phase 2 adds the request serializer for the ``/api/v1/extract/`` development
endpoint. It enforces the input contract (AGENT.md Rule 6): ``text`` must be a
non-empty string within the length bounds configured in settings, and
``source_type`` must be a valid :class:`Claim.InputType`.
"""

from django.conf import settings
from rest_framework import serializers

from .models import Claim


class ExtractRequestSerializer(serializers.Serializer):
    """Validate a claim-extraction request body: ``{"text", "source_type"}``.

    ``text`` is trimmed and length-checked against ``EXTRACT_INPUT_MIN_CHARS`` /
    ``EXTRACT_INPUT_MAX_CHARS``. ``source_type`` defaults to ``"text"`` and must
    be one of the model's input-type choices.
    """

    text = serializers.CharField(trim_whitespace=True)
    source_type = serializers.ChoiceField(
        choices=Claim.InputType.choices, default=Claim.InputType.TEXT
    )

    def validate_text(self, value):
        """Enforce the configured min/max character bounds on the input text."""
        stripped = value.strip()
        min_chars = settings.EXTRACT_INPUT_MIN_CHARS
        max_chars = settings.EXTRACT_INPUT_MAX_CHARS
        if len(stripped) < min_chars:
            raise serializers.ValidationError(
                f"Text must be at least {min_chars} characters."
            )
        if len(stripped) > max_chars:
            raise serializers.ValidationError(
                f"Text must be at most {max_chars} characters."
            )
        return stripped

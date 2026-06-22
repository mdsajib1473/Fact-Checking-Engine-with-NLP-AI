"""Claim orchestration service (Phase 2).

Thin coordination layer that wires the pure NLP stages to the database. It
detects language, extracts claims, and persists each one as a :class:`Claim`
row. Keeping all database writes here — and none in ``claim_extraction.py`` —
preserves the rule that pipeline stages stay independently testable and
side-effect free (AGENT.md Rule 13).
"""

import logging

from ..models import Claim
from .claim_extraction import extract_claims
from .language_service import detect_language

logger = logging.getLogger(__name__)

_VALID_INPUT_TYPES = {choice.value for choice in Claim.InputType}


def process_text_input(raw_text: str, source_type: str) -> list[Claim]:
    """Extract claims from ``raw_text`` and persist each as a :class:`Claim` row.

    Detects the input language, runs claim extraction, and saves one ``Claim``
    per extracted claim with ``raw_text``, ``extracted_claim``, ``language``,
    ``source_input_type``, and ``created_at`` (auto) populated. Returns the list
    of saved ``Claim`` instances (empty when no claim clears the confidence
    threshold). Persistence lives here, never in the extraction stage.

    ``source_type`` must be one of the :class:`Claim.InputType` values
    (``"text"`` / ``"url"``); anything else raises :class:`ValueError`.
    """
    if source_type not in _VALID_INPUT_TYPES:
        raise ValueError(
            f"source_type must be one of {sorted(_VALID_INPUT_TYPES)}, got {source_type!r}"
        )

    language = detect_language(raw_text)
    extracted = extract_claims(raw_text)

    saved = []
    for item in extracted:
        claim = Claim.objects.create(
            raw_text=raw_text,
            extracted_claim=item["claim"],
            # Prefer the per-claim language from extraction; fall back to the
            # document-level detection for safety.
            language=item.get("lang") or language,
            source_input_type=source_type,
        )
        saved.append(claim)

    logger.info(
        "process_text_input: %d claim(s) saved (lang=%s, source=%s)",
        len(saved),
        language,
        source_type,
    )
    return saved

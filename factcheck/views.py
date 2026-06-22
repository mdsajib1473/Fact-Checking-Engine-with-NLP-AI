"""Views for the fact-checking app.

Views stay thin (AGENT.md Rule 7): they validate input, delegate to
``factcheck/services/``, and shape the response. No business logic lives here.
"""

from django.views.generic import TemplateView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import ExtractRequestSerializer
from .services import claim_service
from .services.language_service import detect_language


class HomeView(TemplateView):
    """Render the home page: the text/URL tab switcher shell.

    Phase 1 is visual scaffolding only — there is no submit handling yet.
    """

    template_name = "factcheck/home.html"


class ExtractClaimsView(APIView):
    """POST ``/api/v1/extract/`` — extract and persist claims from raw text.

    Development testing harness for the Phase 2 NLP pipeline (not the final UI
    submission flow, which is wired in Phase 4). Accepts
    ``{"text": ..., "source_type": "text"}``, validates it (AGENT.md Rule 6),
    runs :func:`claim_service.process_text_input`, and returns the extracted
    claims, the detected language, and a count. Invalid input yields 400.
    """

    def post(self, request):
        """Validate the request body, run extraction, and return the result JSON."""
        serializer = ExtractRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        text = serializer.validated_data["text"]
        source_type = serializer.validated_data["source_type"]

        claims = claim_service.process_text_input(text, source_type)
        payload = [
            {
                "claim": claim.extracted_claim,
                "language": claim.language,
            }
            for claim in claims
        ]
        return Response(
            {
                "claims": payload,
                "language": detect_language(text),
                "count": len(payload),
            },
            status=status.HTTP_200_OK,
        )

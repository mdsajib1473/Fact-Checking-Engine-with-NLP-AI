"""URL routes for the fact-checking app."""

from django.urls import path

from .views import ExtractClaimsView, HomeView

app_name = "factcheck"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    # Phase 2 development testing harness for the NLP claim-extraction pipeline.
    path("api/v1/extract/", ExtractClaimsView.as_view(), name="extract"),
]

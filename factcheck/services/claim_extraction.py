"""Claim extraction service (Phase 2) — the core of the NLP pipeline.

Turns raw input text into clean, searchable, verifiable claim strings. The only
public entry point is :func:`extract_claims`; everything else is an internal
helper that other services must not call directly (AGENT.md Rule 13).

Two passes:

* **Pass 1 — spaCy (English only).** A dependency parse over each sentence finds
  subject–verb–object clauses that read as factual assertions. Questions,
  imperatives, opinions, and hedged statements are skipped or scored low.
* **Pass 2 — HuggingFace fallback.** For Bangla text, and for English the parser
  could not confidently handle, a multilingual zero-shot classifier identifies
  and keeps sentences that read as factual claims.

Both models are lazy-loaded module-level singletons: loaded once on first use
(never per request, never at Django startup so boot stays fast), and cached.
If a model cannot load — e.g. the spaCy model isn't installed, or the
transformer won't fit in Render free-tier RAM — extraction *degrades* to a
heuristic sentence pass instead of crashing, keeping the pipeline functional and
unit-testable without a multi-hundred-MB download.

This module is pure (AGENT.md Rule 13): it never writes to the database, calls
an external API, or imports the evidence/verdict stages. Persistence lives in
``claim_service.py``.
"""

import html
import logging
import re
from collections import defaultdict

from django.conf import settings

from .language_service import detect_language

logger = logging.getLogger(__name__)


# --- Heuristic cue sets (English) -------------------------------------------

# Dependency labels marking an object/complement that completes an assertion.
_OBJECT_DEPS = {"dobj", "dative", "attr", "oprd", "acomp", "obj", "pobj"}

# Dependency labels marking the grammatical subject of a clause.
_SUBJECT_DEPS = {"nsubj", "nsubjpass", "csubj", "csubjpass"}

# First-person subjects that usually signal a personal/opinion statement.
_FIRST_PERSON = {"i", "we"}

# Lemmas/words that signal opinion rather than verifiable fact.
_OPINION_CUES = {"think", "believe", "feel", "guess", "suppose", "reckon", "opine"}
_SUBJECTIVE_WORDS = {
    "best", "worst", "amazing", "terrible", "beautiful", "ugly", "delicious",
    "wonderful", "awful", "greatest", "favorite", "favourite", "gorgeous",
    "horrible", "fantastic", "lovely",
}

# Hedging markers that lower confidence in an otherwise factual-looking clause.
_HEDGES = {
    "maybe", "perhaps", "possibly", "might", "could", "allegedly", "reportedly",
    "probably", "apparently", "seemingly", "supposedly",
}

# Zero-shot labels for the Pass 2 transformer classifier.
_FALLBACK_LABELS = ["factual claim", "opinion", "question"]
_FACTUAL_LABEL = "factual claim"


# --- Lazy model singletons --------------------------------------------------

_SPACY_NLP = None
_SPACY_TRIED = False
_HF_PIPE = None
_HF_TRIED = False


def _get_spacy():
    """Return the loaded spaCy English pipeline, or ``None`` if unavailable.

    Loaded once and cached. A failure (model not downloaded, import error) is
    logged and cached as ``None`` so English degrades to the fallback pass
    instead of raising on every call.
    """
    global _SPACY_NLP, _SPACY_TRIED
    if _SPACY_TRIED:
        return _SPACY_NLP
    _SPACY_TRIED = True
    try:
        import spacy

        _SPACY_NLP = spacy.load(settings.SPACY_EN_MODEL)
    except Exception as exc:  # noqa: BLE001 - any load failure must degrade, not crash
        logger.warning(
            "spaCy model '%s' unavailable; English will use the heuristic/HF "
            "fallback instead (%s)",
            settings.SPACY_EN_MODEL,
            exc,
        )
        _SPACY_NLP = None
    return _SPACY_NLP


def _get_hf():
    """Return the lazy-loaded zero-shot transformer pipeline, or ``None``.

    Returns ``None`` immediately when ``ENABLE_HF_FALLBACK`` is off. Otherwise
    loads the multilingual model once and caches it; if loading fails (no
    transformers/torch, or not enough memory) the failure is logged and cached
    as ``None`` so callers fall back to the heuristic pass.
    """
    global _HF_PIPE, _HF_TRIED
    if not getattr(settings, "ENABLE_HF_FALLBACK", True):
        return None
    if _HF_TRIED:
        return _HF_PIPE
    _HF_TRIED = True
    try:
        from transformers import pipeline

        _HF_PIPE = pipeline(
            "zero-shot-classification", model=settings.HF_FALLBACK_MODEL
        )
    except Exception as exc:  # noqa: BLE001 - degrade to heuristic, never crash
        logger.warning(
            "HuggingFace fallback model '%s' unavailable; using heuristic "
            "fallback instead (%s)",
            settings.HF_FALLBACK_MODEL,
            exc,
        )
        _HF_PIPE = None
    return _HF_PIPE


# --- Input sanitization (AGENT.md Rule 12) ----------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_WS_RE = re.compile(r"\s+")


def _sanitize(text: str) -> str:
    """Strip HTML and collapse whitespace; return ``""`` for unusable input.

    All input is untrusted (AGENT.md Rule 12): ``<script>``/``<style>`` blocks
    are dropped wholesale, remaining tags removed, HTML entities unescaped, and
    runs of whitespace collapsed to single spaces.
    """
    if not text or not isinstance(text, str):
        return ""
    text = _SCRIPT_STYLE_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _collapse_ws(text: str) -> str:
    """Collapse internal whitespace runs to single spaces and trim the ends."""
    return _WS_RE.sub(" ", text).strip()


# --- Pass 1: spaCy dependency-parse extraction (English) --------------------


def _clause_head_for(token, head_set):
    """Return the nearest clause-head ancestor of ``token`` (walking ``.head``).

    Used to partition a sentence's tokens among its independent clauses so a
    compound sentence yields one claim per clause.
    """
    current = token
    while current not in head_set and current.head.i != current.i:
        current = current.head
    return current


def _clause_text(tokens):
    """Join ``tokens`` into clean claim text, trimming boundary conjunctions/punct.

    Leading/trailing coordinating conjunctions (e.g. a dangling "and") and
    punctuation left over from splitting a compound sentence are removed.
    """
    ordered = sorted(tokens, key=lambda t: t.i)
    while ordered and (ordered[0].dep_ == "cc" or ordered[0].is_punct or ordered[0].is_space):
        ordered = ordered[1:]
    while ordered and (ordered[-1].dep_ == "cc" or ordered[-1].is_punct or ordered[-1].is_space):
        ordered = ordered[:-1]
    return _collapse_ws("".join(t.text_with_ws for t in ordered))


def _clause_confidence(tokens, head):
    """Score a clause in ``[0, 1]`` by how verifiable a factual assertion it is.

    Rewards a complete subject–verb–object shape, named entities, and concrete
    numbers/dates; penalizes first-person framing, opinion cues, and hedging.
    """
    has_object = any(t.dep_ in _OBJECT_DEPS for t in tokens)
    has_entity = any(t.ent_type_ for t in tokens)
    has_number = any(
        t.like_num or t.ent_type_ in {"DATE", "CARDINAL", "QUANTITY", "PERCENT", "MONEY", "TIME"}
        for t in tokens
    )
    subjects = [t for t in tokens if t.dep_ in _SUBJECT_DEPS and t.head.i == head.i]
    first_person = any(t.lower_ in _FIRST_PERSON for t in subjects)
    has_opinion = any(
        t.lemma_.lower() in _OPINION_CUES or t.lower_ in _SUBJECTIVE_WORDS for t in tokens
    )
    has_hedge = any(t.lower_ in _HEDGES for t in tokens)

    score = 0.5
    if has_object:
        score += 0.2
    if has_entity:
        score += 0.15
    if has_number:
        score += 0.1
    if first_person:
        score -= 0.25
    if has_opinion:
        score -= 0.4
    if has_hedge:
        score -= 0.2
    return round(max(0.0, min(1.0, score)), 2)


def _extract_en_spacy(nlp, text):
    """Extract candidate English claims from ``text`` via spaCy dependency parsing.

    One claim per independent clause. Questions and subject-less clauses
    (imperatives) are skipped; remaining clauses are scored by
    :func:`_clause_confidence`. Returns dicts shaped ``{"claim", "confidence",
    "lang"}`` (unfiltered — the threshold is applied by the caller).
    """
    claims = []
    for sent in nlp(text).sents:
        if sent.text.strip().endswith("?"):
            continue

        # Clause heads: the sentence root plus any *coordinated* verb that has
        # its own subject. Restricting splits to coordination (not complements
        # or subordinate clauses) keeps "A confirmed that B happened" as one
        # claim while splitting "A did X and B did Y" into two.
        head_set = {
            tok
            for tok in sent
            if tok.dep_ == "ROOT"
            or (
                tok.dep_ == "conj"
                and tok.pos_ in {"VERB", "AUX"}
                and any(child.dep_ in _SUBJECT_DEPS for child in tok.children)
            )
        }
        if not head_set:
            continue

        groups = defaultdict(list)
        for tok in sent:
            groups[_clause_head_for(tok, head_set)].append(tok)

        for head, tokens in groups.items():
            has_subject = any(t.dep_ in _SUBJECT_DEPS and t.head.i == head.i for t in tokens)
            if not has_subject:
                continue  # subject-less clause: imperative or fragment, not a claim
            claim_text = _clause_text(tokens)
            if len(claim_text) < 3:
                continue
            claims.append(
                {
                    "claim": claim_text,
                    "confidence": _clause_confidence(tokens, head),
                    "lang": "en",
                }
            )
    return claims


# --- Pass 2: HuggingFace / heuristic fallback -------------------------------

# Capturing split so terminators stay attached to their sentence (lets the
# question check below see a trailing "?"). Handles the Bengali danda (।) and a
# period only when followed by whitespace/end, so "3.14" is not split.
_SENT_SPLIT_RE = re.compile(r"([।!?]+|\.(?=\s|$))")


def _split_sentences(text):
    """Split ``text`` into sentence-like chunks (English periods + Bengali danda).

    Terminating punctuation is kept attached to the sentence it ends.
    """
    pieces = _SENT_SPLIT_RE.split(text)
    sentences = []
    for index in range(0, len(pieces), 2):
        body = pieces[index]
        terminator = pieces[index + 1] if index + 1 < len(pieces) else ""
        sentence = (body + terminator).strip()
        if sentence:
            sentences.append(sentence)
    return sentences


def _has_opinion_cue(sentence):
    """True if a lowercased ``sentence`` contains an English opinion/subjective cue."""
    words = set(re.findall(r"[a-z']+", sentence.lower()))
    return bool(words & _OPINION_CUES or words & _SUBJECTIVE_WORDS)


def _extract_fallback(text, lang):
    """Extract claims from ``text`` for ``lang`` using the transformer or heuristic.

    When the zero-shot pipeline is available, a sentence is kept only if its top
    label is "factual claim" (its score becomes the confidence). When the model
    is unavailable, a heuristic keeps non-question sentences at a fixed
    confidence, lowered when English opinion cues are present. Returns unfiltered
    ``{"claim", "confidence", "lang"}`` dicts.
    """
    pipe = _get_hf()
    claims = []
    for sentence in _split_sentences(text):
        if len(sentence) < 3 or sentence.endswith("?"):
            continue
        if pipe is not None:
            result = pipe(sentence, candidate_labels=_FALLBACK_LABELS, multi_label=False)
            if result["labels"][0] == _FACTUAL_LABEL:
                claims.append(
                    {
                        "claim": sentence,
                        "confidence": round(float(result["scores"][0]), 2),
                        "lang": lang,
                    }
                )
        else:
            confidence = 0.3 if (lang == "en" and _has_opinion_cue(sentence)) else 0.6
            claims.append({"claim": sentence, "confidence": confidence, "lang": lang})
    return claims


# --- Public interface -------------------------------------------------------


def extract_claims(text: str) -> list[dict]:
    """Extract verifiable factual claims from ``text``.

    The single public entry point for claim extraction. Sanitizes the input,
    detects its language, runs the appropriate pass(es), and returns only claims
    at or above ``settings.CLAIM_CONFIDENCE_THRESHOLD``.

    English uses spaCy when it is loaded (the transformer/heuristic fallback is
    reserved for when spaCy is unavailable); Bangla goes straight to the
    fallback pass. Returns an empty list (never raises) for empty, whitespace,
    HTML-only, or unsupported-language input.

    Each returned dict has the shape::

        {"claim": str, "confidence": float, "lang": "en" | "bn"}
    """
    cleaned = _sanitize(text)
    if not cleaned:
        return []

    lang = detect_language(cleaned)
    if lang not in {"en", "bn"}:
        return []

    threshold = settings.CLAIM_CONFIDENCE_THRESHOLD

    if lang == "en":
        nlp = _get_spacy()
        # Trust spaCy when it loaded: an empty result is a confident "no claims"
        # (e.g. a question or pure opinion), not a parser failure. The HF/
        # heuristic fallback is reserved for when spaCy is unavailable, so the
        # transformer never loads for ordinary English input (Render free-tier
        # RAM). Low-confidence English clauses are dropped by the threshold.
        if nlp is not None:
            candidates = _extract_en_spacy(nlp, cleaned)
        else:
            candidates = _extract_fallback(cleaned, "en")
    else:
        candidates = _extract_fallback(cleaned, "bn")

    return [c for c in candidates if c["confidence"] >= threshold]

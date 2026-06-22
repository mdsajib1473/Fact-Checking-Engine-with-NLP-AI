"""Language detection service (Phase 2).

First stage of the claim-extraction pipeline: decide whether input is English
(``"en"``), Bangla (``"bn"``), or something we do not handle (``"unknown"``).
The result routes downstream extraction — English goes through spaCy (Pass 1),
Bangla through the HuggingFace fallback (Pass 2) — and lets the app reply in the
language the user typed (AGENT.md Rule 2).

Detection is **script-first** because this app only supports two languages and
``langdetect`` is unreliable on the short strings users paste — it confidently
mislabels e.g. "Water boils at 100 degrees" as Afrikaans. So:

* Bengali-script text (incl. mostly-Bengali mixes) → ``"bn"``.
* Latin-script text → ``"en"`` (the only Latin-script language we support);
  ``langdetect`` is consulted only to catch the rare romanized-Bangla case,
  never to *reject* English, so no real English claim is ever dropped.
* Text whose letters are neither Latin nor Bengali (Cyrillic, CJK, Arabic, …),
  or which has no letters at all, → ``"unknown"``.

All inputs are treated as untrusted (AGENT.md Rule 12): empty, whitespace-only,
very short, and mixed strings are handled without raising.
"""

from langdetect import DetectorFactory, LangDetectException, detect

# Make langdetect deterministic so detection (and tests) are reproducible.
DetectorFactory.seed = 0

# Bengali Unicode block: U+0980–U+09FF.
_BENGALI_RANGE = (0x0980, 0x09FF)


def _script_counts(text):
    """Return ``(bengali_letters, latin_letters)`` character counts for ``text``.

    Only alphabetic characters are counted; digits, punctuation, and whitespace
    are ignored. Letters that are neither ASCII-Latin nor Bengali (e.g. Cyrillic
    or CJK) count toward neither total, so other-script text falls through to
    ``"unknown"``.
    """
    bengali = latin = 0
    for char in text:
        if _BENGALI_RANGE[0] <= ord(char) <= _BENGALI_RANGE[1]:
            bengali += 1
        elif char.isascii() and char.isalpha():
            latin += 1
    return bengali, latin


def detect_language(text: str) -> str:
    """Detect the language of ``text`` as ``"en"``, ``"bn"``, or ``"unknown"``.

    Returns ``"unknown"`` for empty/whitespace-only input, text with no
    alphabetic content, or text written in a script other than Latin/Bengali.
    Bengali-script text (including English/Bangla mixes that are mostly Bengali)
    returns ``"bn"``. Latin-script text returns ``"en"`` unless ``langdetect``
    identifies it as Bangla. Never raises on malformed or tiny input.
    """
    if not text or not text.strip():
        return "unknown"

    bengali, latin = _script_counts(text)

    if bengali == 0 and latin == 0:
        return "unknown"

    # Bengali-dominant (or pure Bengali) text routes to the Bangla pipeline.
    if bengali > 0 and bengali >= latin:
        return "bn"

    # Latin-dominant: English unless langdetect spots romanized Bangla. We never
    # downgrade Latin text to "unknown" — langdetect is too unreliable on short
    # input to be trusted for rejecting English.
    try:
        if detect(text.strip()) == "bn":
            return "bn"
    except LangDetectException:
        pass
    return "en"

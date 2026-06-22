"""Django settings for the Fact-Checking Engine (project: core).

All secrets and environment-specific values are read from a `.env` file via
python-dotenv (AGENT.md Rule 6 — never hardcode secrets). See `.env.example`
for the full list of keys.
"""

from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from a local .env file if present.
load_dotenv(BASE_DIR / ".env")


def env_bool(key, default=False):
    """Read a boolean env var, accepting 1/true/yes/on (case-insensitive)."""
    return os.environ.get(key, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(key, default=""):
    """Read a comma-separated env var into a list of trimmed, non-empty values."""
    return [item.strip() for item in os.environ.get(key, default).split(",") if item.strip()]


# --- Core security ---

DEBUG = env_bool("DJANGO_DEBUG", default=False)

# SECRET_KEY must come from the environment. A throwaway key is allowed only in
# DEBUG so local dev works out of the box; production must set DJANGO_SECRET_KEY.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "django-insecure-dev-only-do-not-use-in-production"
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DEBUG is False.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", default="127.0.0.1,localhost")

# https origins trusted for CSRF (e.g. https://your-app.onrender.com on Render).
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")


# --- Applications ---

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "factcheck",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise serves collected static files in production (Render).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"


# --- Database (Neon Postgres via NEON_DATABASE_URL) ---
# Falls back to local SQLite when NEON_DATABASE_URL is unset so the project runs
# locally without credentials. Neon requires SSL, so ssl_require=True forces
# sslmode=require on the parsed connection.

NEON_DATABASE_URL = os.environ.get("NEON_DATABASE_URL")
if NEON_DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            NEON_DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# --- Password validation ---

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Authentication redirects (django.contrib.auth) ---

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "factcheck:home"
LOGOUT_REDIRECT_URL = "factcheck:home"


# --- Internationalization ---
# English + Bangla are supported from the start (AGENT.md Section 2).

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# --- Static files (WhiteNoise) ---

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- NLP / claim extraction (Phase 2) ---
# Thresholds and model names live here, never hardcoded in services (AGENT.md
# Rule 7). Override any of these via the environment without touching code.


def env_float(key, default):
    """Read a float env var, falling back to ``default`` if unset or unparseable."""
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def env_int(key, default):
    """Read an int env var, falling back to ``default`` if unset or unparseable."""
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return int(default)


# Minimum confidence a candidate claim must reach to be returned (0.0–1.0).
CLAIM_CONFIDENCE_THRESHOLD = env_float("CLAIM_CONFIDENCE_THRESHOLD", 0.5)

# spaCy English pipeline used for Pass 1 dependency-parse extraction. Installed
# once via `python -m spacy download en_core_web_sm` (see README, NLP model setup).
SPACY_EN_MODEL = os.environ.get("SPACY_EN_MODEL", "en_core_web_sm")

# Multilingual HuggingFace model for the Pass 2 fallback (Bangla + low-confidence
# English). Lazy-loaded on first use; if it cannot load (e.g. Render free-tier
# RAM), claim extraction degrades to a heuristic fallback rather than crashing.
HF_FALLBACK_MODEL = os.environ.get(
    "HF_FALLBACK_MODEL", "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
)

# Set to "0"/"false" to skip the transformer entirely and always use the
# heuristic fallback (useful for fast CI and tight-memory deploys).
ENABLE_HF_FALLBACK = env_bool("ENABLE_HF_FALLBACK", default=True)

# Length bounds for the /api/v1/extract/ development endpoint (AGENT.md Rule 6).
EXTRACT_INPUT_MIN_CHARS = env_int("EXTRACT_INPUT_MIN_CHARS", 10)
EXTRACT_INPUT_MAX_CHARS = env_int("EXTRACT_INPUT_MAX_CHARS", 5000)


# --- Production hardening (active only when DEBUG is False) ---
# Foundational flags for Render; deeper hardening (HSTS preload, rate limiting)
# lands in Phase 5.

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

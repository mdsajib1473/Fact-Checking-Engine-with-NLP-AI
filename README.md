![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.2-092E20?style=flat-square&logo=django&logoColor=white)
![DRF](https://img.shields.io/badge/Django%20REST-Framework-A30000?style=flat-square&logo=django&logoColor=white)
![Postgres](https://img.shields.io/badge/Database-Neon%20Postgres-336791?style=flat-square&logo=postgresql&logoColor=white)
![pgvector](https://img.shields.io/badge/pgvector-enabled-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Tailwind](https://img.shields.io/badge/Tailwind-CSS-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)
![spaCy](https://img.shields.io/badge/NLP-spaCy-09A3D5?style=flat-square&logo=spacy&logoColor=white)
![HuggingFace](https://img.shields.io/badge/NLP-HuggingFace-FFD21E?style=flat-square&logo=huggingface&logoColor=black)
![Groq](https://img.shields.io/badge/LLM-Groq-F55036?style=flat-square)
![Deployment](https://img.shields.io/badge/Deploy-Render-46E3B7?style=flat-square&logo=render&logoColor=white)
![Status](https://img.shields.io/badge/Status-In%20Development-orange?style=flat-square)

# Fact-Checking Engine with NLP-AI

An AI-powered fact-checking system that extracts verifiable claims from text or
URLs, cross-references trusted sources, and returns a transparent, source-cited
verdict. See [AGENT.md](AGENT.md) for the locked tech stack, rules, structure,
and database schema.

> **Phase status:** Phase 2 (Claim Extraction Pipeline) complete - spaCy +
> HuggingFace NLP extraction with English/Bangla support. Evidence retrieval,
> the verdict engine, and the real UI arrive in later phases.

## Tech stack (Phase 1)

- **Backend:** Django 5.2 + Django REST Framework
- **Database:** Neon (serverless Postgres) via `dj-database-url`, with pgvector
- **Frontend:** Django templates + Tailwind CSS (manual Tailwind CLI build)
- **Auth:** Django's built-in `django.contrib.auth`
- **Deployment:** Render.com (free tier) + WhiteNoise for static files

### Why manual Tailwind CLI (not django-tailwind)?

The locked project structure (AGENT.md Section 4) puts `package.json` and
`tailwind.config.js` at the repo root and outputs to
`factcheck/static/factcheck/css/tailwind_output.css`. The manual Tailwind CLI
matches this exactly, keeps Python dependencies lean, and avoids the extra
`theme` app that `django-tailwind` would introduce (which isn't in the locked
structure).

## Local setup

1. **Create a virtualenv and install dependencies**

   ```bash
   python -m venv venv
   venv/Scripts/python -m pip install -r requirements.txt   # Windows
   # source venv/bin/activate && pip install -r requirements.txt  # macOS/Linux
   ```

2. **Configure environment**

   ```bash
   cp .env.example .env
   ```

   Fill in `DJANGO_SECRET_KEY`. Leave `NEON_DATABASE_URL` blank to use local
   SQLite, or set it to your Neon connection string (must end with
   `?sslmode=require`) to use Neon.

3. **Build Tailwind CSS**

   ```bash
   npm install
   npm run build:css        # one-off build
   # npm run watch:css      # rebuild on change during development
   ```

4. **Run migrations and start the server**

   ```bash
   venv/Scripts/python manage.py migrate
   venv/Scripts/python manage.py runserver
   ```

## NLP model setup (Phase 2)

The claim-extraction pipeline uses two models. Neither ships in
`requirements.txt` — they are one-time downloads so the dependency install stays
lean and reproducible.

1. **spaCy English model** (`en_core_web_sm`, ~13 MB) — used for the English
   dependency-parse pass. Download it once after installing requirements:

   ```bash
   venv/Scripts/python -m spacy download en_core_web_sm   # Windows
   # python -m spacy download en_core_web_sm               # macOS/Linux
   ```

2. **HuggingFace fallback model**
   (`MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`, ~560 MB) — a multilingual
   zero-shot classifier used for **Bangla** text and as a fallback when spaCy is
   unavailable. It downloads **automatically on first use** and is cached under
   `~/.cache/huggingface`; no manual step is required.

   To skip the transformer entirely (e.g. tight-memory environments or fast CI),
   set `ENABLE_HF_FALLBACK=0` — extraction then degrades to a heuristic sentence
   pass instead of loading the model. `torch` is installed as the CPU-only build
   to stay within Render's free tier.

### Try the extraction endpoint

With the server running, the Phase 2 development harness accepts raw text:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/extract/ \
  -H "Content-Type: application/json" \
  -d '{"text": "The Earth orbits the Sun. Water boils at 100 degrees Celsius.", "source_type": "text"}'
```

## Neon + pgvector (required before migrating against Neon)

The `ClaimEmbedding` model uses a pgvector column. **Before running migrations
against a Neon database**, enable the extension once in the Neon SQL editor:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

This is intentionally **not** a Django migration so the local SQLite fallback
keeps working. Neon requires SSL - the connection string must include
`?sslmode=require` (enforced in `settings.py` via `ssl_require=True`).

## Deployment (Render)

`render.yaml` defines the web service. `build.sh` installs dependencies, builds
Tailwind CSS, runs `collectstatic`, and applies migrations. Set the secrets
(`NEON_DATABASE_URL`, `DJANGO_SECRET_KEY`, API keys, `DJANGO_ALLOWED_HOSTS`,
`DJANGO_CSRF_TRUSTED_ORIGINS`) as environment variables in the Render dashboard.

## Project layout

See [AGENT.md](AGENT.md) Section 4 for the full, locked structure.
# AGENT.md — Fact-Checking Engine with NLP-AI

**Domain:** InfoTech / Social Media
**Portfolio role:** Project 2 of 3 — AI for Truth & Information Integrity
**Built with:** Claude Code (Pro subscription), 5-phase structured workflow

---

## 1. Project Overview

An AI-powered fact-checking system that accepts any text, URL, or social media post, extracts its verifiable factual claims, cross-references them against trusted knowledge sources, and returns a transparent, source-cited verdict (Supported / Disputed / False / Unverifiable). Built entirely on free-tier tools to remain zero-cost during development and early deployment.

---

## 2. Locked Tech Stack

| Layer | Choice |
|---|---|
| Backend | Django + Django REST Framework |
| Frontend | Django templates + Tailwind CSS + pure Tailwind (no component library) + vanilla JS where interactivity is needed |
| Database | Neon (serverless hosted Postgres, free tier — no project-count cap, unlike Supabase) |
| Auth | Django's built-in auth system (`django.contrib.auth`), since Neon doesn't bundle an auth layer |
| Vector storage | pgvector (Neon extension — enabled per-database via `CREATE EXTENSION vector;`) |
| NLP (claim extraction) | spaCy + HuggingFace transformers (both — spaCy for speed, HuggingFace as fallback for harder cases) |
| LLM (verdict reasoning) | Groq free tier (Llama 3 / Mixtral) |
| Evidence sources | Wikipedia API, Wikidata SPARQL, Google Fact Check Tools API |
| Async tasks | Django BackgroundTasks (no Celery/Redis — keep infra minimal) |
| Caching | Postgres table-based cache with TTL (no Redis) |
| Deployment | Render.com (free tier) |
| UI interaction | Tab switcher — paste text OR enter URL |
| Verdict display | Full report view — claim-by-claim breakdown with expandable evidence panels, plus a simple-view toggle for non-technical users |
| Theming | Dark mode supported (Tailwind `dark:` classes) |
| Language support | English + Bangla (বাংলা) from the start, auto-detected |

---

## 3. Rules

1. Never build beyond the current step.
2. Always respond in the same language the user typed (Bangla → Bangla).
3. Every verdict result MUST include the disclaimer:
   "This is an AI-generated assessment, not a final ruling on truth. Verify with the cited sources."
4. Commit and push code if/when necessary with 3 to 5 words.
5. Write clean, well-commented code — every function and class must have a docstring.
6. Follow secure coding practices — never expose secrets, always use CSRF protection, validate and sanitize all user inputs before processing.
7. Write scalable code — keep business logic in services/, keep views thin, never hardcode values that belong in settings or .env.
8. Do not over-comment — only comment where the code is not self-explanatory. Avoid stating the obvious (e.g. `# increment counter` above `i += 1`).
9. Never let the LLM output a verdict without at least one source citation attached — if no evidence is retrieved, the verdict must default to "Unverifiable", never "False" or "True".
10. Always show the user the raw evidence snippet and source link behind a verdict — no black-box scoring. Transparency is a core requirement, not a nice-to-have.
11. Respect free-tier API limits — implement caching (Postgres table) for every external API call (Groq, Google Fact Check, Wikipedia, Wikidata) so repeated claims don't burn quota. Always check cache before calling an external API.
12. Treat all scraped or user-submitted text as untrusted — never pass raw HTML or unsanitized scraped content directly into an LLM prompt; strip and clean it first.
13. Keep claim extraction, evidence retrieval, and verdict scoring as separate, independently testable service functions — never merge pipeline stages into one function, even for speed.
14. Log every verdict decision (claim, sources used, score, timestamp) to the database for auditability — fact-checking systems must be able to explain past decisions.
15. Never silently fail on a failed external API call — catch the error, fall back to the next available free source in priority order, and only return "Unverifiable" if all sources are exhausted.

---

## 4. Project Structure

```
fact-checking-engine/
├── manage.py
├── requirements.txt
├── .env.example
├── render.yaml
├── core/                      # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── factcheck/                 # Main Django app
│   ├── models.py              # Claim, Verdict, Source, CacheEntry
│   ├── views.py                # thin views only
│   ├── urls.py
│   ├── serializers.py
│   ├── services/
│   │   ├── claim_extraction.py   # spaCy + HuggingFace pipeline
│   │   ├── evidence_retrieval.py # Wikipedia, Wikidata, Google Fact Check
│   │   ├── verdict_engine.py     # Groq LLM scoring logic
│   │   ├── cache_service.py      # Postgres cache read/write + TTL (Neon)
│   │   ├── language_service.py   # Bangla/English detection
│   │   └── scraper_service.py    # URL → clean text, sanitization
│   ├── templates/factcheck/
│   │   ├── base.html
│   │   ├── home.html              # tab switcher: text / URL input
│   │   └── report.html            # claim-by-claim verdict report
│   ├── static/factcheck/
│   │   ├── css/tailwind_output.css
│   │   └── js/report_interactions.js
│   └── tests/
├── tailwind.config.js
└── AGENT.md                   # this file — living document, updated each phase
```

---

## 5. Database Schema (Neon / Postgres)

**claims**
- id (uuid, pk)
- raw_text (text)
- extracted_claim (text)
- source_input_type (enum: text / url)
- source_url (text, nullable)
- language (enum: en / bn)
- created_at (timestamp)

**verdicts**
- id (uuid, pk)
- claim_id (fk → claims)
- label (enum: supported / disputed / false / unverifiable)
- confidence_score (integer, 0–10)
- explanation (text)
- created_at (timestamp)

**sources**
- id (uuid, pk)
- verdict_id (fk → verdicts)
- source_name (text)
- source_url (text)
- evidence_snippet (text)
- relevance_score (float)

**cache_entries**
- id (uuid, pk)
- cache_key (text, indexed, unique)
- api_name (text)
- response_payload (jsonb)
- expires_at (timestamp)

**claim_embeddings** (pgvector)
- id (uuid, pk)
- claim_id (fk → claims)
- embedding (vector)

---

## 6. Five-Phase Build Plan

### Phase 1 — Foundation: Django + Neon + Project Scaffold
Set up Django project, connect to Neon Postgres, define models and migrations, configure environment variables, set up Tailwind build pipeline, create base template with dark mode toggle and language switcher shell. No AI logic yet — pure scaffolding.

### Phase 2 — Claim Extraction Pipeline (NLP)
Build the `claim_extraction.py` service using spaCy for fast dependency-parse extraction, with HuggingFace transformers as a fallback for ambiguous cases. Output clean, searchable claim strings. Unit test against sample English and Bangla text.

### Phase 3 — Evidence Retrieval
Build `evidence_retrieval.py` integrating Wikipedia API, Wikidata SPARQL, and Google Fact Check Tools API, each wrapped with the Supabase-based cache layer and TTL. Implement the fallback chain (rule 15) so a failed source doesn't break the pipeline.

### Phase 4 — Verdict Engine + UI
Build `verdict_engine.py` using the Groq free-tier LLM for chain-of-thought verdict reasoning with mandatory source citation (rule 9). Build the Tailwind UI: tab switcher (text/URL input), full report view with expandable evidence panels, simple-view toggle, dark mode, and Bangla/English rendering.

### Phase 5 — Security, Logging & Deployment
Harden CSRF protection, input sanitization, rate limiting via Django middleware, add the verdict audit log (rule 14), write final tests, and deploy to Render with environment variables configured securely.

---

## 7. Open Items / Notes
*(Update this section as decisions are made during development)*

**Phase 1 — Completed:** Django (`core`) + `factcheck` app scaffolded; 5 models with UUID PKs + initial migration; Neon wired via `dj-database-url` (SSL-required, SQLite local fallback); env-driven secrets via python-dotenv; Tailwind CLI pipeline (dark mode `class`); base/home templates with dark-mode toggle + language switcher shell; built-in auth URLs; Render `render.yaml` + `build.sh`. `check` passes, Tailwind + collectstatic verified, and migrations apply cleanly against the live Neon database (Postgres 18.4, pgvector 0.8.1) — all 5 tables created, `claim_embeddings.embedding` confirmed as a real `vector` column.

- [x] Confirm Neon Postgres project created and connection string added to `.env`
      *(Connected to Neon Postgres 18.4; `migrate` applied cleanly.)*
- [x] Confirm `pgvector` extension enabled on the Neon database (`CREATE EXTENSION vector;`)
      *(Enabled on Neon, version 0.8.1. Kept out of migrations so the local SQLite fallback still works.)*
- [x] Confirm Google Fact Check Tools API key obtained and added to `.env`
- [x] Confirm Groq API key obtained and added to `.env`
- [ ] Decide on rate-limit thresholds per IP (placeholder: 10 requests/hour for unauthenticated users) *(Phase 5)*
- [ ] Decide on Bangla NLP model specifics if spaCy's Bangla support proves insufficient *(Phase 2)*
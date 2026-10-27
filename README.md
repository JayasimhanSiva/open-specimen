# Open Specimen

An index of ten open-source typefaces with a live type tester, an AI font matcher, and an AI help assistant that answers FAQs, explains error codes and opens support tickets.

**Live site:** _deployment in progress — link added after the first deploy_
**Repository:** https://github.com/JayasimhanSiva/open-specimen

Built with Django 6.1 in VS Code, tested end to end with Playwright.

---

## Assessment checklist

| Requirement | Where it is |
|---|---|
| Responsive website, at least 3 pages | Home, Typeface pages, FAQ, Error codes, Health, Sign up / Log in, Submit. Layout uses a 12 / 8 / 4-column grid for desktop / tablet / phone. |
| Chat widget on every page | `myapp/templates/myapp/_assistant.html`, included by `base.html` and by the standalone `500.html` |
| 10+ FAQs stored in SQL, shown on the FAQ page | `Faq` model, 15 entries seeded by migration `0006_seed_help`, page at `/faq/` |
| 8+ error codes (400, 401, 403, 404, 429, 500, 503 + one site-specific) | `ErrorCode` model, 9 codes (adds 405 and the site-specific **OS-422**), page at `/errors/` |
| Custom 404 and 500 pages with "Ask the assistant" | `myapp/templates/myapp/error.html` (400 / 403 / 404) and `myapp/templates/500.html`, wired in `myproject/urls.py` |
| AI assistant: answers from FAQ data, explains error codes, creates a ticket when it can't answer | `Assistant` in `myapp/views.py`, API at `/api/chat/` and `/api/tickets/` |
| Support tickets in SQL | `SupportTicket` model (reference like `T-00012`), visible in `/admin/` |
| Chat logs and feedback in MongoDB | `chat_logs` and `feedback` collections, `DocumentStore` in `myapp/models.py` |
| API keys in environment variables, nothing confidential in Git | All secrets read from the environment (`.env.example` lists them); `.env` and the database are in `.gitignore` |
| Request logging | `RequestLogMiddleware`: one line per request with request id, method, path, status, time, user and a hashed IP; `X-Request-ID` header on every response |
| Health check page | `/health/` (page) and `/health.json` (for monitors): SQL, MongoDB, AI model and GitHub API status, uptime, request counts. Returns 503 if the database is down. |
| One extra third-party API with a time limit and fallback | GitHub REST API: typeface pages show the font's last change in `google/fonts`. Hard 1.5 s connect / 2.5 s read limit; on failure the last good answer is reused, otherwise a clear "unavailable" message. |
| README with live link and one proposed improvement | This file; see [Proposed improvement](#proposed-improvement) |

## How the AI works

Both AI features use a small open-source embedding model, **BAAI/bge-small-en-v1.5**, run locally on the CPU through `fastembed` (ONNX). It's free, needs no API key, and answers in a few milliseconds.

- **Assistant.** The question is compared with every FAQ (its question, other phrasings, and its answer) and every error code. Above 0.80 similarity it answers, between 0.745 and 0.80 it answers as a best guess, and below that it says it can't answer and offers a support ticket. A message that names a code (`404`, `error OS-422`) is explained straight from the `ErrorCode` table. Each exchange is logged to MongoDB, and visitors can rate each answer.
- **Font matcher** (for logged-in users). It picks the typeface whose uses and mood best match a description, and sets its variable axes (weight, width, optical size and others) to fit.
- **Fallback.** If the model can't load, both features fall back to keyword matching instead of failing.

## Project structure

```
myproject/
├── manage.py
├── myproject/
│   ├── settings.py        environment-driven settings (SQL, MongoDB, security, logging)
│   ├── urls.py            routes + custom error handlers
│   └── wsgi.py
└── myapp/
    ├── models.py          Typeface, Match, Faq, ErrorCode, SupportTicket, Submission + MongoDB store
    ├── views.py           pages, assistant, font matcher, APIs, health, request logging, error pages
    ├── urls.py
    ├── templates/         base, home, typeface, faq, errors, health, auth, error pages, chat widget
    ├── static/            site.css, site.js
    ├── migrations/        schema + seed data (typefaces, FAQs, error codes)
    ├── admin.py
    └── tests.py           52 Playwright browser tests
```

## Run it locally

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m playwright install chromium
copy .env.example .env          # macOS/Linux: cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/. Without `MONGODB_URI`, chat logs are kept in memory and `/health/` shows MongoDB as "not configured".

Run the tests (they use an in-memory MongoDB and a fake GitHub, so they need no network):

```bash
python manage.py test myapp
```

## Environment variables

| Name | Required | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | in production | Django signing key. The app refuses to start without it when `DJANGO_DEBUG` is off. |
| `DJANGO_DEBUG` | no | `1` for local development only |
| `DATABASE_URL` | in production | PostgreSQL connection string. If unset, a local SQLite file is used. |
| `MONGODB_URI` | in production | MongoDB connection string (e.g. MongoDB Atlas) for chat logs and feedback |
| `MONGODB_DB` | no | Database name, default `open_specimen` |
| `GITHUB_TOKEN` | no | Raises the GitHub API limit from 60 to 5000 requests per hour |
| `DJANGO_ALLOWED_HOSTS` | outside Render | Comma-separated hostnames |

## Deploy (Render)

`render.yaml` describes a web service and a free PostgreSQL database:

1. In Render, choose **New → Blueprint** and select this repository.
2. When asked, paste your MongoDB Atlas connection string into `MONGODB_URI`.
3. Render installs dependencies, downloads the AI model during the build, runs migrations on start, and serves the site over HTTPS.

## Error codes

| Code | Meaning |
|---|---|
| 400 | Bad request: malformed form or JSON |
| 401 | Not logged in: the font matcher needs an account |
| 403 | Forbidden: expired form token, or a cross-site API call |
| 404 | Page not found |
| 405 | Method not allowed: a POST-only address opened directly |
| 429 | Too many requests: over 20 chat messages or 30 matches a minute |
| 500 | Server error |
| 503 | Service unavailable: the health check can't reach the database |
| **OS-422** | Site-specific: the font matcher's description is empty or too short |

## Proposed improvement

**Write the answers with a generative model, grounded in the FAQ.** Today the assistant returns the stored FAQ answer word for word. The next step is to send the three closest FAQs and the question to a hosted language model, with the API key in an environment variable and a time limit, and have it write one short answer that cites its source FAQ. It would fall back to the current exact-match answer on timeout. The chat logs and ratings already stored in MongoDB would show which questions it gets wrong, and those can be turned into new FAQs.

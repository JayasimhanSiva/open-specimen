# Open Specimen

An index of 40 open-source typefaces with a live type tester, an AI font matcher, and an AI type assistant on every page. The assistant recommends fonts for any project, suggests pairings, compares typefaces, gives you the CSS, reviews the typography of your own website, answers FAQs, explains error codes and opens support tickets.

**Live site:** https://open-specimen.onrender.com (free Render instance: after 15 idle minutes the first visit takes about a minute to wake it up)
**Repository:** https://github.com/JayasimhanSiva/open-specimen

Built with Django 6.1 in VS Code, tested end to end with Playwright.

---

## Assessment checklist

| Requirement | Where it is |
|---|---|
| Responsive website, at least 3 pages | Home, 40 typeface pages, FAQ, Error codes, Health, Sign up / Log in, Submit, Staff dashboard. Layout uses a 12 / 8 / 4-column grid for desktop / tablet / phone. |
| Chat widget on every page | `myapp/templates/myapp/_assistant.html`, included by `base.html` and by the standalone `500.html` |
| 10+ FAQs stored in SQL, shown on the FAQ page | `Faq` model, 27 entries (site help and typography advice) seeded by migrations, page at `/faq/` |
| 8+ error codes (400, 401, 403, 404, 429, 500, 503 + one site-specific) | `ErrorCode` model, 9 codes (adds 405 and the site-specific **OS-422**), page at `/errors/` |
| Custom 404 and 500 pages with "Ask the assistant" | `myapp/templates/myapp/error.html` (400 / 403 / 404) and `myapp/templates/500.html`, wired in `myproject/urls.py` |
| AI assistant: answers from FAQ data, explains error codes, creates a ticket when it can't answer | `Assistant` and `TypeAdvisor` in `myapp/views.py`, API at `/api/chat/` and `/api/tickets/` |
| Support tickets in SQL | `SupportTicket` model (reference like `T-00012`), managed on `/staff/` and in `/admin/` |
| Chat logs and feedback in MongoDB | `chat_logs` and `feedback` collections, `DocumentStore` in `myapp/models.py`, shown on `/staff/` |
| API keys in environment variables, nothing confidential in Git | All secrets read from the environment (`.env.example` lists them); `.env` and the database are in `.gitignore` |
| Request logging | `RequestLogMiddleware`: one line per request with request id, method, path, status, time, user and a hashed IP; `X-Request-ID` header on every response |
| Health check page | `/health/` (page) and `/health.json` (for monitors): SQL, MongoDB, AI model and GitHub API status, uptime, request counts. Returns 503 if the database is down. |
| One extra third-party API with a time limit and fallback | GitHub REST API: typeface pages show the font's last change in `google/fonts`. Hard 1.5 s connect / 2.5 s read limit; on failure the last good answer is reused, otherwise a clear "unavailable" message. |
| README with live link and one proposed improvement | This file; see [Proposed improvement](#proposed-improvement) |

## What the assistant can do

| Ask | It does |
|---|---|
| "Which font should I use for a yoga studio website?" | Recommends a typeface for that kind of project, explains why, suggests a body-text partner, and gives copy-ready CSS plus a link to the tester with the settings applied |
| "Review https://mysite.com" or "suggest fonts for mysite.com" | Opens the page, reads its HTML and CSS, finds the fonts, body size and line height, and lists **what to change, where and why**, with CSS to copy |
| "What pairs with Fraunces?" | Suggests a contrasting partner, with heading and body roles and CSS |
| "Inter vs Roboto Flex" | Compares the two: style, designer, mood, best uses, flexibility |
| "How do I use JetBrains Mono in CSS?" | Gives the Google Fonts link tag and the `font-family` rule |
| "What line height should I use?", "how many fonts?" | Answers from 12 typography FAQs |
| "What does 429 mean?", "error OS-422" | Explains the error code and what to do |
| Anything it can't answer | Says so and offers to open a support ticket |

Every exchange is logged to MongoDB and every answer can be rated. Website reviews only open public addresses: localhost, private networks, odd ports and non-web schemes are refused, every hop is checked, and each review has a time and size limit.

## How the AI works

The AI is a small open-source embedding model, **BAAI/bge-small-en-v1.5**, run locally on the CPU through `fastembed` (ONNX). It's free, needs no API key, and answers in milliseconds.

- **Understanding the question.** The question is embedded and compared with every FAQ (its question, other phrasings and answer), every error code, and every typeface's uses and mood. Intent rules then route it to a recommendation, a pairing, a comparison, a CSS snippet, a website review or an FAQ answer.
- **Choosing fonts.** The font matcher scores each typeface by how closely the project matches the jobs it's good for and how it feels. It then sets variable axes such as weight, width and optical size by comparing the description with opposite anchor phrases ("bold" or "light", "wide" or "narrow").
- **Fallback.** If the model can't load, everything falls back to keyword matching instead of failing.

## Accounts and admin

- **Visitors** can browse everything, use the assistant, and read the FAQ and error codes without an account.
- **Members** sign up with name, email, username and password, then log in with their username. They can use the font matcher, keep a match history and submit typefaces.
- **Staff** see a **Staff** link that opens `/staff/`, a dashboard with account, ticket and chat numbers. From there they can work through support tickets (open, answered, closed), read recent chats and the questions the assistant couldn't answer, and track the share of answers rated helpful. Full editing of FAQs, error codes, typefaces and users is in the Django admin at `/admin/`.

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
    ├── views.py           pages, assistant, type advisor, font matcher, APIs, staff dashboard, health, logging
    ├── urls.py
    ├── templates/         base, home, typeface, faq, errors, health, staff, auth, error pages, chat widget
    ├── static/            site.css, site.js
    ├── migrations/        schema + seed data (40 typefaces, FAQs, error codes)
    ├── admin.py
    └── tests.py           61 Playwright browser tests
```

## Run it locally

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m playwright install chromium
copy .env.example .env          # macOS/Linux: cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/. Without `MONGODB_URI`, chat logs are kept in memory and `/health/` shows MongoDB as "not configured".

Run the tests. They use an in-memory MongoDB and fake GitHub and website responses, so they need no network:

```bash
python manage.py test myapp
```

## Testing

- **61 Playwright browser tests** cover:
  - every page and the chat widget on each one
  - sign-up, username log-in and log-out
  - the staff dashboard
  - the font matcher, with and without JavaScript
  - assistant recommendations, pairings, comparisons, CSS and website reviews
  - private-address refusal, injection and odd input (HTML, SQL, emoji, other languages, 500-character messages)
  - tickets, ratings and the 404 / 500 pages
  - the health check, request logging, and the GitHub timeout fallback
  - no sideways scrolling at five screen widths
- **Stress tests** were run during development:
  - a scroll test of all 49 pages at phone, tablet and desktop widths (no console errors, failed requests or overflow)
  - 600 concurrent page requests (no server errors)
  - the chat rate limit under load
  - more than 100 varied assistant prompts, including reviews of real public websites
- **Live checks** against https://open-specimen.onrender.com, run with Playwright:
  - every page on desktop and phone over HTTPS, with no sideways scrolling and the chat widget present
  - the custom 404 and its "Ask the assistant" button
  - no console errors
  - assistant answers to FAQs, error codes, recommendations, pairings and website reviews

## Running on a small server

The free Render instance has 512 MB of memory and a tenth of a CPU, and the code is tuned for that:
- The AI model runs on one thread with small batches, which peaks at about 260 MB instead of over 700 MB.
- The embeddings of every typeface, FAQ and error code are computed during the build and loaded at startup.
- Requests that arrive while the model is still loading are answered by keyword matching instead of waiting.
- MongoDB writes happen on a background thread, so a slow database never delays an answer.

## Environment variables

| Name | Required | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | in production | Django signing key. The app refuses to start without it when `DJANGO_DEBUG` is off. |
| `DJANGO_DEBUG` | no | `1` for local development only |
| `DATABASE_URL` | in production | PostgreSQL connection string. If unset, a local SQLite file is used. |
| `MONGODB_URI` | in production | MongoDB connection string (e.g. MongoDB Atlas) for chat logs and feedback |
| `MONGODB_DB` | no | Database name, default `open_specimen` |
| `DJANGO_SUPERUSER_USERNAME`, `_EMAIL`, `_PASSWORD` | on Render | Creates the admin account on first deploy |
| `GITHUB_TOKEN` | no | Raises the GitHub API limit from 60 to 5000 requests per hour |
| `DJANGO_ALLOWED_HOSTS` | outside Render | Comma-separated hostnames |

## Deploy (Render)

`render.yaml` describes a web service and a free PostgreSQL database:

1. In MongoDB Atlas, open **Network Access** and allow `0.0.0.0/0`, because Render's addresses change.
2. In Render, choose **New → Blueprint** and select this repository.
3. Fill in `MONGODB_URI` (your Atlas connection string, with your database password) and the three `DJANGO_SUPERUSER_*` values for your admin account.
4. Render installs dependencies, downloads the AI model during the build, runs migrations, creates the admin account and serves the site over HTTPS.

## Error codes

| Code | Meaning |
|---|---|
| 400 | Bad request: malformed form or JSON |
| 401 | Not logged in: the font matcher needs an account |
| 403 | Forbidden: expired form token, a cross-site API call, or the staff dashboard without staff rights |
| 404 | Page not found |
| 405 | Method not allowed: a POST-only address opened directly |
| 429 | Too many requests: over 20 chat messages, 6 website reviews or 30 matches a minute |
| 500 | Server error |
| 503 | Service unavailable: the health check can't reach the database |
| **OS-422** | Site-specific: the font matcher's description is empty or too short |

## Proposed improvement

**Write the answers with a generative model, grounded in the site's data.** Today the assistant picks the best stored answer and fills sentence templates. The next step is to send the closest FAQs, typeface records or website findings to a hosted language model, with the API key in an environment variable and a time limit, and have it write one short, conversational answer that cites its sources. It would fall back to the current answer on timeout. The unanswered questions and ratings already collected on the staff dashboard would show where it still goes wrong, and those can be turned into new FAQs.

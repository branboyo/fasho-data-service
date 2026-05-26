# fasho-data-service

Backend service that discovers companies hiring on ATS platforms and stores their job listings in Supabase.

Currently supports **Lever** and **Ashby HQ**.

## How it works

The pipeline runs in two stages:

### Stage 1 — Token collection
1. **Brave Search** queries `site:jobs.lever.co` and `site:ashbyhq.com` across 20 job-role terms (e.g. "software engineer", "devops", "machine learning"), exhausting all terms for each site before moving to the next.
2. **Sanitization** filters to matching URLs, extracts the company token (slug) and a clean base URL, strips job titles from company names, and deduplicates by token.
3. **Supabase upload** upserts results into the `tokens` table with `url` as the unique constraint.

### Stage 2 — Job collection
1. Tokens are read from the `tokens` table filtered by `ats`.
2. Each company's postings are fetched directly from the ATS public API, rate-limited to 9 req/sec.
3. Results are written to a local `.txt` file.

---

## Setup

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv).

```bash
uv sync
```

Create `local-settings.yaml` in the project root:

```
BRAVE_SEARCH_API_KEY=your-brave-api-key
SUPABASE_API_URL=https://your-project.supabase.co
SUPABASE_API_KEY=your-service-role-key
```

> Environment variables `FASHO_BRAVE_API_KEY`, `FASHO_SUPABASE_URL`, `FASHO_SUPABASE_KEY` override the file if set.

Get a Brave Search API key at https://api-dashboard.search.brave.com/

---

## Running the pipeline

### Stage 1 — Collect company tokens

Searches all terms across Lever and Ashby, prints a per-site/per-term summary, and upserts discovered companies into Supabase.

```bash
uv run python -m app.services.token_collection.brave_search
```

**Output:**
```
INFO  Starting fetch: 2 site(s) × 20 term(s) × 5 page(s) = 200 requests
INFO  ── site: jobs.lever.co ──
INFO    "tech"                         → 12 listing(s) from 20 raw
INFO    "software engineer"            → 9 listing(s) from 20 raw
...
INFO  ── site: ashbyhq.com ──
INFO    "tech"                         → 7 listing(s) from 20 raw
...
INFO  Done. Total listings: 183

Results summary:
  jobs.lever.co:
    tech: 12 listings
    software engineer: 9 listings
    ...
  ashbyhq.com:
    tech: 7 listings
    ...

Upserted 183 row(s) into tokens
```

---

### Stage 2 — Fetch job listings

Run each collector independently. Both read tokens from Supabase and write results to a local `.txt` file.

#### Lever

```bash
uv run python -m app.services.job_collection.lever_jobs
```

Output file: `lever_job_listings.txt`

#### Ashby HQ

```bash
uv run python -m app.services.job_collection.ashbyhq_jobs
```

Output file: `ashby_job_listings.txt`

> **Note:** Both collectors default to `TOKEN_LIMIT = 2` for safety during development. Increase this constant in each file when ready for a full run.

---

## Running tests

```bash
uv run --extra dev pytest
```

---

## Project structure

```
app/
  config.py                            # Settings (local-settings.yaml + env vars)
  main.py                              # FastAPI app
  services/
    token_collection/
      brave_search.py                  # Brave Search client + QueryRotator + CLI
      supabase_upload.py               # Supabase upsert logic
    job_collection/
      lever_jobs.py                    # Lever Postings API client + CLI
      ashbyhq_jobs.py                  # Ashby HQ Posting API client + CLI
tests/
  test_brave_search.py
  test_lever_jobs.py
  test_supabase_upload.py
local-settings.yaml                    # Local credentials (gitignored)
```

---

## Supabase schema

```sql
create table public.tokens (
  id           uuid primary key default gen_random_uuid(),
  token        text not null,
  company_name text not null,
  origin_query text not null,
  ats          text not null,
  url          text not null unique,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
```

| Column | Type | Description |
|---|---|---|
| `url` | text (unique) | Base URL for the company's job board |
| `company_name` | text | Company name extracted from the search result title |
| `origin_query` | text | Search term that surfaced this company |
| `ats` | text | `"lever"` or `"ashbyhq"` |
| `token` | text | Company slug used to call the ATS API |

---

## ATS API reference

| ATS | Endpoint |
|---|---|
| Lever | `https://api.lever.co/v0/postings/{token}` |
| Ashby HQ | `https://api.ashbyhq.com/posting-api/job-board/{token}` |

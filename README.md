# fasho-data-service

Backend service that discovers companies hiring on ATS platforms (starting with Lever) and stores them in Supabase.

## How it works

1. **Brave Search** queries `site:jobs.lever.co` across 20 job-role terms (e.g. "software engineer", "devops", "machine learning"), paginating up to 100 raw results per term.
2. **Sanitization** filters to Lever-only URLs, extracts the company token and clean URL (`https://jobs.lever.co/{token}/`), strips job titles from company names, and deduplicates by token.
3. **Supabase upload** upserts the results into a `tokens` table with `url` as the unique constraint.

## Setup

Requires Python 3.12+.

```bash
uv sync
```

Create `local-settings.yaml` in the project root:

```
BRAVE_SEARCH_API_KEY=your-brave-api-key
SUPABASE_API_URL=https://your-project.supabase.co
SUPABASE_API_KEY=your-service-role-key
```

Environment variables (`FASHO_BRAVE_API_KEY`, `FASHO_SUPABASE_URL`, `FASHO_SUPABASE_KEY`) override the file if set.

## Usage

### Run the token collection pipeline

```bash
uv run python -m app.services.token_collection.brave_search
```

Searches all terms, prints a summary, and uploads to Supabase if credentials are configured.

### Run the API server

```bash
uv run uvicorn app.main:app --reload
```

### Run tests

```bash
uv run --extra dev pytest
```

## Project structure

```
app/
  config.py                          # Settings from local-settings.yaml + env vars
  main.py                            # FastAPI app
  services/
    token_collection/
      brave_search.py                # Brave Search client, sanitization, CLI entrypoint
      supabase_upload.py             # Supabase upsert logic
tests/
  test_brave_search.py
  test_supabase_upload.py
local-settings.yaml                  # Local credentials (gitignored)
```

## Supabase schema

The `tokens` table must have a unique constraint on `url`. Columns:

| Column | Type | Description |
|---|---|---|
| `url` | text (unique) | `https://jobs.lever.co/{token}/` |
| `company_name` | text | Company name from search result |
| `origin_query` | text | Search term that found this company |
| `ats` | text | `"lever"` |
| `token` | text | Company slug (e.g. `skywarditsolutions`) |

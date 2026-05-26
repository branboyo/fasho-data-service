"""Brave Search API client for discovering Lever ATS company tokens."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field, replace
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
LEVER_DOMAIN = "jobs.lever.co"
ASHBYHQ_DOMAIN = "ashbyhq.com"
RESULTS_PER_TERM = 100

# ── Data models ───────────────────────────────────────────────────────────────


@dataclass
class LeverListing:
    """A deduplicated company entry discovered on Lever."""

    url: str            # e.g. https://jobs.lever.co/acme/
    company_name: str   # title with trailing " - …" stripped
    origin_query: str   # the search term that surfaced this result
    ats: str            # always "lever"
    token: str          # company slug from the URL path


@dataclass
class QueryRotator:
    """Cycles through site-scoped search terms for the Brave API.

    Exhausts all *terms* for the first site before moving to the next::

        sites=[A, B], terms=[1, 2]  →  A+1, A+2, B+1, B+2, A+1, …
    """

    sites: list[str]
    terms: list[str]
    _index: int = field(default=0, init=False, repr=False)

    @property
    def total(self) -> int:
        """Total number of unique (site, term) combinations."""
        return len(self.sites) * len(self.terms)

    def next(self) -> str:
        """Return the next ``site:<site> <term>`` query and advance."""
        i = self._index % self.total
        site = self.sites[i // len(self.terms)]
        term = self.terms[i % len(self.terms)]
        self._index += 1
        query = f"site:{site} {term}"
        log.debug("QueryRotator [%d/%d] site=%r → %r", i + 1, self.total, site, query)
        return query

    def reset(self) -> None:
        self._index = 0

    @property
    def current_index(self) -> int:
        return self._index % self.total


@dataclass
class SearchConfig:
    """Brave Web Search request parameters.

    See https://api.search.brave.com/app/documentation/web-search/query
    """

    count: int = 20
    offset: int = 0
    country: str = "US"
    search_lang: str = "en"
    ui_lang: str = "en-US"
    safesearch: str = "moderate"
    freshness: str | None = None
    spellcheck: bool = True
    text_decorations: bool = True
    extra_snippets: bool = False
    operators: bool = True
    result_filter: list[str] | None = None
    units: str | None = None

    def to_params(self, query: str) -> dict:
        """Build the query-string dict, clamping values to API limits."""
        params: dict = {
            "q": query[:400],
            "count": max(1, min(self.count, 20)),
            "offset": max(0, min(self.offset, 9)),
            "country": self.country,
            "search_lang": self.search_lang,
            "ui_lang": self.ui_lang,
            "safesearch": self.safesearch,
            "spellcheck": str(self.spellcheck).lower(),
            "text_decorations": str(self.text_decorations).lower(),
            "extra_snippets": str(self.extra_snippets).lower(),
            "operators": str(self.operators).lower(),
        }
        if self.freshness:
            params["freshness"] = self.freshness
        if self.result_filter:
            params["result_filter"] = ",".join(self.result_filter)
        if self.units:
            params["units"] = self.units
        return params


# ── Predefined query sets ─────────────────────────────────────────────────────

JOB_QUERIES = QueryRotator(
    sites=[LEVER_DOMAIN, ASHBYHQ_DOMAIN],
    terms=[
        "tech",
        "software engineer",
        "data engineer",
        "frontend developer",
        "backend developer",
        "devops",
        "product manager",
        "machine learning",
        "full stack",
        "cloud engineer",
        "qa engineer",
        "security",
        "mobile",
        "forward deployed",
        "AI",
        "cybersecurity",
        "mid-level engineer",
        "developer",
        "machine learning engineer",
        "tech lead",
    ],
)

# ── Sanitization ─────────────────────────────────────────────────────────────


def _build_headers(api_key: str) -> dict:
    return {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "x-subscription-token": api_key,
    }


def _extract_web_results(data: dict) -> list[dict]:
    return data.get("web", {}).get("results", [])


def _sanitize_company_name(title: str) -> str:
    """Strip everything after the first `` - `` separator."""
    return title.split(" - ", 1)[0].strip()


def _extract_token(raw_url: str, site: str) -> tuple[str, str]:
    """Return ``(clean_url, token)`` for the given *site* domain.

    The token is always the first meaningful path segment (company slug)::

        https://jobs.lever.co/acme/abc-123      →  ("https://jobs.lever.co/acme/", "acme")
        https://jobs.ashbyhq.com/acme/abc-123   →  ("https://jobs.ashbyhq.com/acme/", "acme")
    """
    parsed = urlparse(raw_url)
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return raw_url, ""
    token = parts[0]
    return f"https://{parsed.netloc}/{token}/", token


_SITE_ATS: dict[str, str] = {
    LEVER_DOMAIN: "lever",
    ASHBYHQ_DOMAIN: "ashbyhq",
}


def sanitize_results(
    raw_results: list[dict],
    origin_query: str,
    site: str,
) -> list[LeverListing]:
    """Convert raw Brave results into deduplicated ``LeverListing`` objects.

    * Filters to results that belong to *site*.
    * Deduplicates by company token (first occurrence wins).
    * Sanitizes URLs and company names.
    """
    ats = _SITE_ATS.get(site, site)
    seen_tokens: set[str] = set()
    listings: list[LeverListing] = []

    for r in raw_results:
        raw_url = r.get("url", "")
        if site not in raw_url:
            continue

        clean_url, token = _extract_token(raw_url, site)
        if not token or token in seen_tokens:
            continue

        seen_tokens.add(token)
        listings.append(LeverListing(
            url=clean_url,
            company_name=_sanitize_company_name(r.get("title", "")),
            origin_query=origin_query,
            ats=ats,
            token=token,
        ))

    return listings


# ── API functions ─────────────────────────────────────────────────────────────


async def search_jobs(
    api_key: str,
    rotator: QueryRotator,
    config: SearchConfig | None = None,
) -> list[LeverListing]:
    """Run a single Brave search page and return sanitized listings."""
    cfg = config or SearchConfig()
    query = rotator.next()

    # Determine which site this query targets so sanitization filters correctly.
    site = next((s for s in rotator.sites if f"site:{s}" in query), rotator.sites[0])
    origin = query.removeprefix(f"site:{site} ")
    params = cfg.to_params(query)

    log.debug("GET %s params=%s", BRAVE_SEARCH_URL, params)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            BRAVE_SEARCH_URL,
            headers=_build_headers(api_key),
            params=params,
            timeout=15.0,
        )

    log.debug("Response %s for query %r", resp.status_code, query)
    resp.raise_for_status()

    raw = _extract_web_results(resp.json())
    listings = sanitize_results(raw, origin, site)
    log.info("Query %r → %d listing(s)", query, len(listings))
    return listings


async def fetch_all_terms(
    api_key: str,
    rotator: QueryRotator,
    *,
    config: SearchConfig | None = None,
    results_per_term: int = RESULTS_PER_TERM,
) -> dict[str, dict[str, list[LeverListing]]]:
    """Fetch every (site, term) combination, paginating each to *results_per_term* hits.

    Returns a two-level dict keyed by ``site → term → listings``::

        {
            "jobs.lever.co":   {"tech": [...], "software engineer": [...], ...},
            "ashbyhq.com":     {"tech": [...], "software engineer": [...], ...},
        }

    Defaults to ``freshness="pw"`` (past week) unless overridden via *config*.
    """
    cfg = config or SearchConfig(freshness="pw")
    pages = max(1, results_per_term // cfg.count)
    results: dict[str, dict[str, list[LeverListing]]] = {s: {} for s in rotator.sites}
    rotator.reset()

    log.info(
        "Starting fetch: %d site(s) × %d term(s) × %d page(s) = %d requests",
        len(rotator.sites), len(rotator.terms), pages,
        len(rotator.sites) * len(rotator.terms) * pages,
    )

    async with httpx.AsyncClient() as client:
        for site in rotator.sites:
            log.info("── site: %s ──", site)
            for term in rotator.terms:
                query = f"site:{site} {term}"
                all_raw: list[dict] = []

                for offset in range(pages):
                    page_cfg = replace(cfg, offset=offset)
                    params = page_cfg.to_params(query)

                    log.debug("GET offset=%d  %r", offset, query)
                    resp = await client.get(
                        BRAVE_SEARCH_URL,
                        headers=_build_headers(api_key),
                        params=params,
                        timeout=15.0,
                    )
                    log.debug("Response %s for %r offset=%d", resp.status_code, query, offset)
                    resp.raise_for_status()

                    body = resp.json()
                    if "web" not in body:
                        log.warning("No 'web' key for %r offset=%d — response: %s", query, offset, body)

                    raw = _extract_web_results(body)
                    all_raw.extend(raw)

                    if len(raw) < cfg.count:
                        log.debug("Page %d short (%d results), stopping pagination", offset, len(raw))
                        break

                term_listings = sanitize_results(all_raw, term, site)
                log.info("  %-30s → %d listing(s) from %d raw", f'"{term}"', len(term_listings), len(all_raw))
                results[site][term] = term_listings

    total = sum(len(lst) for terms in results.values() for lst in terms.values())
    log.info("Done. Total listings: %d", total)
    return results


# ── CLI entrypoint ────────────────────────────────────────────────────────────


async def main(api_key: str | None = None) -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    from app.config import settings

    key = api_key or settings.brave_api_key
    if not key:
        raise ValueError("brave_api_key not set in local-settings.yaml or FASHO_BRAVE_API_KEY")

    results = await fetch_all_terms(key, JOB_QUERIES)

    print("\nResults summary:")
    for site, terms in results.items():
        print(f"\n  {site}:")
        for term, items in terms.items():
            print(f"    {term}: {len(items)} listings")
            for listing in items:
                print(f"      [{listing.ats}] {listing.token}: {listing.url}")

    if settings.supabase_url and settings.supabase_key:
        from app.services.token_collection.supabase_upload import get_client, upload_all_terms

        client = get_client(settings.supabase_url, settings.supabase_key)
        uploaded = upload_all_terms(client, results)
        print(f"\nUploaded {len(uploaded)} listing(s) to Supabase")
    else:
        print("\nSkipping Supabase upload (supabase_url / supabase_key not configured)")


if __name__ == "__main__":
    import sys

    api_key = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(main(api_key))

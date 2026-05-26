"""Fetch job listings from the Ashby HQ Posting API for tokens stored in Supabase."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

import httpx
from supabase import Client

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

ASHBY_API_URL = "https://api.ashbyhq.com/posting-api/job-board"
TOKEN_LIMIT = 2  # Hardcoded limit for testing — increase when ready
MAX_REQUESTS_PER_SECOND = 9
TABLE = "tokens"

# ── Rate limiter ──────────────────────────────────────────────────────────────


class RateLimiter:
    """Sliding-window rate limiter using an asyncio semaphore.

    Allows at most *max_per_second* requests to start within any rolling
    1-second window. Each ``acquire()`` takes a slot that is automatically
    released 1 second later.
    """

    def __init__(self, max_per_second: int = MAX_REQUESTS_PER_SECOND):
        self._sem = asyncio.Semaphore(max_per_second)

    async def acquire(self) -> None:
        await self._sem.acquire()
        asyncio.get_running_loop().call_later(1.0, self._sem.release)


# ── Supabase queries ──────────────────────────────────────────────────────────


def fetch_ashby_tokens(client: Client, *, limit: int = TOKEN_LIMIT) -> list[str]:
    """Return up to *limit* tokens from the ``tokens`` table where ats='ashbyhq'."""
    result = (
        client.table(TABLE)
        .select("token")
        .eq("ats", "ashbyhq")
        .limit(limit)
        .execute()
    )
    tokens = [row["token"] for row in result.data]
    log.info("Fetched %d ashbyhq token(s) from Supabase", len(tokens))
    return tokens


# ── Ashby API ─────────────────────────────────────────────────────────────────


async def fetch_jobs_for_token(
    http_client: httpx.AsyncClient,
    token: str,
    rate_limiter: RateLimiter,
) -> list[dict]:
    """Fetch all postings for a single company token, respecting the rate limit."""
    await rate_limiter.acquire()
    url = f"{ASHBY_API_URL}/{token}"
    log.debug("GET %s", url)

    resp = await http_client.get(url, timeout=15.0)
    resp.raise_for_status()

    body = resp.json()
    if not body.get("jobPostingApiEnabled", False):
        log.warning("  %s — job posting API not enabled", token)
        return []

    return body.get("jobs", [])


async def fetch_all_jobs(
    supabase_client: Client,
    *,
    limit: int = TOKEN_LIMIT,
) -> dict[str, list[dict]]:
    """Fetch job listings for all ashbyhq tokens, rate-limited to 9 req/sec.

    Returns a dict mapping each token to its list of job postings.
    """
    tokens = fetch_ashby_tokens(supabase_client, limit=limit)
    if not tokens:
        log.warning("No ashbyhq tokens found in Supabase")
        return {}

    rate_limiter = RateLimiter()

    async def _fetch_one(token: str) -> tuple[str, list[dict]]:
        try:
            jobs = await fetch_jobs_for_token(http_client, token, rate_limiter)
            log.info("  %s → %d job(s)", token, len(jobs))
            return token, jobs
        except httpx.HTTPStatusError as e:
            log.warning("  %s → HTTP %s", token, e.response.status_code)
            return token, []

    async with httpx.AsyncClient() as http_client:
        pairs = await asyncio.gather(*(_fetch_one(t) for t in tokens))

    return dict(pairs)


# ── Output ────────────────────────────────────────────────────────────────────


def export_results(
    results: dict[str, list[dict]],
    output_file: str | Path = "ashby_job_listings.txt",
) -> Path:
    """Write job listings to a human-readable text file."""
    output_path = Path(output_file)
    total_jobs = sum(len(jobs) for jobs in results.values())

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"Ashby HQ Job Listings — {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write(f"Companies: {len(results)}  |  Jobs: {total_jobs}\n")
        f.write("=" * 80 + "\n")

        for token, jobs in results.items():
            f.write(f"\n{token} ({len(jobs)} job{'s' if len(jobs) != 1 else ''})\n")
            f.write("-" * 80 + "\n")

            if not jobs:
                f.write("  (No listings found)\n")
                continue

            for i, job in enumerate(jobs, 1):
                title = job.get("title", "Untitled")
                job_id = job.get("id", "")
                department = job.get("departmentName", "")
                team = job.get("teamName", "")
                location = job.get("locationName", "")
                is_remote = job.get("isRemote", False)
                employment_type = job.get("employmentType", "")
                job_url = job.get("jobUrl", "")
                updated_at = job.get("updatedAt")
                published_at = job.get("publishedDate")
                description = job.get("descriptionPlain", "").strip()
                compensation = job.get("compensation", {})

                f.write(f"\n  {i}. {title}\n")
                if job_id:
                    f.write(f"     ID:           {job_id}\n")
                if department:
                    f.write(f"     Department:   {department}\n")
                if team:
                    f.write(f"     Team:         {team}\n")
                if location:
                    f.write(f"     Location:     {location}\n")
                if is_remote:
                    f.write(f"     Remote:       Yes\n")
                if employment_type:
                    f.write(f"     Type:         {employment_type}\n")
                if compensation:
                    min_val = compensation.get("minValue")
                    max_val = compensation.get("maxValue")
                    currency = compensation.get("currencyCode", "")
                    interval = compensation.get("interval", "")
                    if min_val and max_val:
                        f.write(f"     Compensation: {currency} {min_val}–{max_val} / {interval}\n")
                if published_at:
                    f.write(f"     Published:    {published_at}\n")
                if updated_at:
                    f.write(f"     Updated:      {updated_at}\n")
                if job_url:
                    f.write(f"     URL:          {job_url}\n")
                if description:
                    f.write(f"     Description:\n")
                    for line in description.splitlines():
                        f.write(f"       {line}\n")

        f.write(f"\n{'=' * 80}\n")

    log.info("Exported %d jobs across %d companies to %s", total_jobs, len(results), output_path)
    return output_path


# ── CLI entrypoint ────────────────────────────────────────────────────────────


async def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    from app.config import settings
    from app.services.token_collection.supabase_upload import get_client

    if not settings.supabase_url or not settings.supabase_key:
        raise ValueError("supabase_url / supabase_key not configured")

    supabase = get_client(settings.supabase_url, settings.supabase_key)
    results = await fetch_all_jobs(supabase)

    print(f"\nResults: {sum(len(j) for j in results.values())} jobs across {len(results)} companies")
    for token, jobs in results.items():
        print(f"  {token}: {len(jobs)} job(s)")

    output = export_results(results)
    print(f"\nExported to {output.absolute()}")


if __name__ == "__main__":
    asyncio.run(main())

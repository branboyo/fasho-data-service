"""Fetch job listings from the Lever Postings API for tokens stored in Supabase."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

import httpx
from supabase import Client

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

LEVER_API_URL = "https://api.lever.co/v0/postings"
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


def fetch_lever_tokens(client: Client, *, limit: int = TOKEN_LIMIT) -> list[str]:
    """Return up to *limit* tokens from the ``tokens`` table where ats='lever'."""
    result = (
        client.table(TABLE)
        .select("token")
        .eq("ats", "lever")
        .limit(limit)
        .execute()
    )
    tokens = [row["token"] for row in result.data]
    log.info("Fetched %d lever token(s) from Supabase", len(tokens))
    return tokens


# ── Lever API ─────────────────────────────────────────────────────────────────


async def fetch_jobs_for_token(
    http_client: httpx.AsyncClient,
    token: str,
    rate_limiter: RateLimiter,
) -> list[dict]:
    """Fetch all postings for a single company token, respecting the rate limit."""
    await rate_limiter.acquire()
    url = f"{LEVER_API_URL}/{token}"
    log.debug("GET %s", url)

    resp = await http_client.get(url, timeout=15.0)
    resp.raise_for_status()
    return resp.json()


async def fetch_all_jobs(
    supabase_client: Client,
    *,
    limit: int = TOKEN_LIMIT,
) -> dict[str, list[dict]]:
    """Fetch job listings for all lever tokens, rate-limited to 9 req/sec.

    Returns a dict mapping each token to its list of job postings.
    """
    tokens = fetch_lever_tokens(supabase_client, limit=limit)
    if not tokens:
        log.warning("No lever tokens found in Supabase")
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
    output_file: str | Path = "lever_job_listings.txt",
) -> Path:
    """Write job listings to a human-readable text file."""
    output_path = Path(output_file)
    total_jobs = sum(len(jobs) for jobs in results.values())

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"Lever Job Listings — {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write(f"Companies: {len(results)}  |  Jobs: {total_jobs}\n")
        f.write("=" * 80 + "\n")

        for token, jobs in results.items():
            f.write(f"\n{token} ({len(jobs)} job{'s' if len(jobs) != 1 else ''})\n")
            f.write("-" * 80 + "\n")

            if not jobs:
                f.write("  (No listings found)\n")
                continue

            for i, job in enumerate(jobs, 1):
                title = job.get("text", "Untitled")
                cats = job.get("categories", {})
                hosted_url = job.get("hostedUrl", "")
                apply_url = job.get("applyUrl", "")
                posting_id = job.get("id", "")
                created_at = job.get("createdAt")
                workplace = job.get("workplaceType", "")
                description = job.get("descriptionPlain", "").strip()
                additional = job.get("additional", "").strip()
                lists = job.get("lists", [])
                all_locations = cats.get("allLocations", [])

                f.write(f"\n  {i}. {title}\n")
                if posting_id:
                    f.write(f"     ID:          {posting_id}\n")
                if cats.get("location"):
                    f.write(f"     Location:    {cats['location']}\n")
                if len(all_locations) > 1:
                    f.write(f"     All Loc:     {', '.join(all_locations)}\n")
                if cats.get("department"):
                    f.write(f"     Department:  {cats['department']}\n")
                if cats.get("commitment"):
                    f.write(f"     Type:        {cats['commitment']}\n")
                if cats.get("team"):
                    f.write(f"     Team:        {cats['team']}\n")
                if workplace:
                    f.write(f"     Workplace:   {workplace}\n")
                if created_at:
                    f.write(f"     Created:     {datetime.fromtimestamp(created_at / 1000):%Y-%m-%d}\n")
                if hosted_url:
                    f.write(f"     URL:         {hosted_url}\n")
                if apply_url:
                    f.write(f"     Apply:       {apply_url}\n")
                if description:
                    f.write(f"     Description:\n")
                    for line in description.splitlines():
                        f.write(f"       {line}\n")
                if lists:
                    for section in lists:
                        f.write(f"     {section.get('text', '')}:\n")
                        for item in section.get("content", "").split("\n"):
                            item = item.strip()
                            if item:
                                f.write(f"       - {item}\n")
                if additional:
                    f.write(f"     Additional:\n")
                    for line in additional.splitlines():
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

"""Upload sanitized Lever listings to Supabase."""

from __future__ import annotations

import logging
from dataclasses import asdict

from supabase import Client, create_client

from app.services.token_collection.brave_search import LeverListing

log = logging.getLogger(__name__)

TABLE = "tokens"


def get_client(url: str, key: str) -> Client:
    """Create a Supabase client."""
    return create_client(url, key)


def upsert_listings(client: Client, listings: list[LeverListing]) -> list[dict]:
    """Upsert listings into the ``tokens`` table, deduplicating on ``url``."""
    if not listings:
        return []

    rows = [asdict(listing) for listing in listings]
    result = client.table(TABLE).upsert(rows, on_conflict="url").execute()
    log.info("Upserted %d row(s) into %s", len(result.data), TABLE)
    return result.data


def upload_all_terms(
    client: Client,
    results: dict[str, list[LeverListing]],
) -> list[dict]:
    """Deduplicate listings across all search terms, then upsert in one batch."""
    all_listings: list[LeverListing] = []
    seen_tokens: set[str] = set()

    for listings in results.values():
        for listing in listings:
            if listing.token not in seen_tokens:
                seen_tokens.add(listing.token)
                all_listings.append(listing)

    log.info("Uploading %d unique listing(s) across %d term(s)", len(all_listings), len(results))
    return upsert_listings(client, all_listings)

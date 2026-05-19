import hashlib
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job


def normalize_title(title: str) -> str:
    title = title.lower().strip()
    title = re.sub(r"[^a-z0-9\s]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title


def compute_dedup_hash(company_id: int, title: str, location: str | None) -> str:
    normalized = normalize_title(title)
    loc = (location or "").lower().strip()
    payload = f"{company_id}|{normalized}|{loc}"
    return hashlib.sha256(payload.encode()).hexdigest()


async def is_duplicate(
    session: AsyncSession, dedup_hash: str, window_days: int = 3
) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    stmt = select(Job.id).where(
        Job.dedup_hash == dedup_hash,
        Job.first_seen_at >= cutoff,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None

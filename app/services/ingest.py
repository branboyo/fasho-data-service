from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.schemas.job import RawJob
from app.services.dedup import compute_dedup_hash, is_duplicate
from app.services.geocode import GeocodeService


@dataclass
class IngestResult:
    stored: int = 0
    skipped: int = 0


def parse_schedule(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.lower().strip()
    if any(t in raw for t in ["full-time", "full time", "ft"]):
        return "full_time"
    if any(t in raw for t in ["part-time", "part time", "pt"]):
        return "part_time"
    return None


def parse_posted_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


class IngestService:
    def __init__(self, geocoder: GeocodeService):
        self.geocoder = geocoder

    async def ingest_jobs(
        self,
        company_id: int,
        source: str,
        industry: str | None,
        raw_jobs: list[RawJob],
        session: AsyncSession,
    ) -> IngestResult:
        result = IngestResult()

        for raw in raw_jobs:
            dedup_hash = compute_dedup_hash(company_id, raw.title, raw.location_raw)

            if await is_duplicate(session, dedup_hash):
                result.skipped += 1
                continue

            coords = None
            wkt = None
            if raw.location_raw:
                coords = await self.geocoder.geocode(raw.location_raw)
            if coords:
                wkt = f"SRID=4326;POINT({coords[1]} {coords[0]})"

            job = Job(
                company_id=company_id,
                title=raw.title,
                description=raw.description,
                location_geo=wkt,
                location_text=raw.location_raw,
                pay_min=raw.pay_min,
                pay_max=raw.pay_max,
                schedule_type=parse_schedule(raw.schedule_raw),
                source=source,
                source_url=raw.apply_url,
                posted_at=parse_posted_at(raw.posted_at),
                raw_payload=raw.raw_payload,
                industry=industry,
                dedup_hash=dedup_hash,
            )
            session.add(job)
            result.stored += 1

        if result.stored > 0:
            await session.commit()

        return result

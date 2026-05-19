import logging

import httpx
from arq import cron
from sqlalchemy import select

from app.ats.registry import get_client
from app.config import settings
from app.database import async_session
from app.models.company import Company
from app.services.geocode import GeocodeService
from app.services.ingest import IngestService

logger = logging.getLogger(__name__)


async def poll_company(ctx: dict, company_id: int):
    async with async_session() as session:
        company = await session.get(Company, company_id)
        if company is None:
            logger.warning("Company %d not found, skipping", company_id)
            return None

        async with httpx.AsyncClient(timeout=30.0) as http:
            client = get_client(company.ats_type, company.ats_config, http)
            raw_jobs = await client.fetch_jobs()

        geocoder = GeocodeService(user_agent=settings.geocode_user_agent)
        ingest = IngestService(geocoder=geocoder)
        result = await ingest.ingest_jobs(
            company_id=company.id,
            source=company.ats_type.value,
            industry=company.industry,
            raw_jobs=raw_jobs,
            session=session,
        )

        logger.info(
            "Polled %s (%s): stored=%d skipped=%d",
            company.name,
            company.ats_type.value,
            result.stored,
            result.skipped,
        )
        return result


async def schedule_all_polls(ctx: dict):
    async with async_session() as session:
        result = await session.execute(select(Company))
        companies = result.scalars().all()

    for company in companies:
        await ctx["redis"].enqueue_job("poll_company", company.id)

    logger.info("Scheduled polls for %d companies", len(companies))


class WorkerSettings:
    functions = [poll_company]
    cron_jobs = [cron(schedule_all_polls, minute={0, 10, 20, 30, 40, 50})]
    redis_settings = settings.redis_url

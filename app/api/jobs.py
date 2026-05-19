from fastapi import APIRouter, Depends
from sqlalchemy import select, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.job import Job
from app.schemas.matching import JobMatch, MatchRequest
from app.services.matching import compute_match_score

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/match", response_model=list[JobMatch])
async def match_jobs(req: MatchRequest, session: AsyncSession = Depends(get_session)):
    stmt = (
        select(Job)
        .where(
            Job.industry.in_(req.industries),
            or_(Job.pay_max.is_(None), Job.pay_max >= req.pay_floor),
            Job.first_seen_at > text("now() - interval '14 days'"),
        )
        .order_by(Job.first_seen_at.desc())
        .limit(200)
    )

    if req.schedules:
        stmt = stmt.where(Job.schedule_type.in_(req.schedules))

    result = await session.execute(stmt)
    jobs = result.scalars().all()

    scored = []
    for job in jobs:
        s = compute_match_score(job, req)
        scored.append(
            JobMatch(
                id=job.id,
                company_id=job.company_id,
                title=job.title,
                description=job.description,
                location_text=job.location_text,
                pay_min=float(job.pay_min) if job.pay_min else None,
                pay_max=float(job.pay_max) if job.pay_max else None,
                schedule_type=job.schedule_type,
                source_url=job.source_url,
                industry=job.industry,
                score=s,
            )
        )

    scored.sort(key=lambda m: m.score, reverse=True)
    return scored[:50]

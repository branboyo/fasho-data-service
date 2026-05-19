from datetime import datetime, timezone

from app.models.job import Job
from app.schemas.matching import MatchRequest

W_INDUSTRY = 0.30
W_SKILLS = 0.25
W_RECENCY = 0.20
W_PAY = 0.15
W_SCHEDULE = 0.10


def compute_match_score(job: Job, prefs: MatchRequest) -> float:
    score = 0.0

    if job.industry and job.industry in prefs.industries:
        score += W_INDUSTRY

    if job.description and prefs.hard_skills:
        desc_lower = job.description.lower()
        hits = sum(1 for s in prefs.hard_skills if s.lower() in desc_lower)
        score += W_SKILLS * (hits / len(prefs.hard_skills))

    if job.first_seen_at:
        age_h = (datetime.now(timezone.utc) - job.first_seen_at).total_seconds() / 3600
        if age_h < 24:
            score += W_RECENCY
        elif age_h < 72:
            score += W_RECENCY * 0.75
        elif age_h < 168:
            score += W_RECENCY * 0.5
        else:
            score += W_RECENCY * 0.25

    if prefs.pay_floor and job.pay_max is not None:
        if job.pay_max >= prefs.pay_floor:
            score += W_PAY
    elif not prefs.pay_floor:
        score += W_PAY

    if prefs.schedules and job.schedule_type:
        if job.schedule_type in prefs.schedules:
            score += W_SCHEDULE
    elif not prefs.schedules:
        score += W_SCHEDULE

    return round(score, 2)

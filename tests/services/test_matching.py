from datetime import datetime, timedelta, timezone

from tests.conftest import make_job
from app.schemas.matching import MatchRequest
from app.services.matching import compute_match_score


def _prefs(**overrides) -> MatchRequest:
    defaults = dict(
        latitude=37.7749,
        longitude=-122.4194,
        industries=["Retail"],
        schedules=["full_time"],
        pay_floor=17.0,
        hard_skills=["POS systems", "customer service"],
    )
    defaults.update(overrides)
    return MatchRequest(**defaults)


class TestComputeMatchScore:
    def test_perfect_match_scores_high(self):
        job = make_job(
            industry="Retail",
            schedule_type="full_time",
            pay_max=22.0,
            first_seen_at=datetime.now(timezone.utc),
        )
        score = compute_match_score(job, _prefs())
        assert score >= 0.8

    def test_wrong_industry_loses_industry_weight(self):
        job = make_job(industry="Healthcare")
        full = compute_match_score(job, _prefs())
        job_match = make_job(industry="Retail")
        matched = compute_match_score(job_match, _prefs())
        assert matched > full

    def test_old_job_scores_lower_on_recency(self):
        recent = make_job(first_seen_at=datetime.now(timezone.utc))
        old = make_job(first_seen_at=datetime.now(timezone.utc) - timedelta(days=10))
        assert compute_match_score(recent, _prefs()) > compute_match_score(old, _prefs())

    def test_pay_below_floor_loses_pay_weight(self):
        good_pay = make_job(pay_max=22.0)
        low_pay = make_job(pay_max=15.0)
        prefs = _prefs(pay_floor=17.0)
        assert compute_match_score(good_pay, prefs) > compute_match_score(low_pay, prefs)

    def test_score_is_between_0_and_1(self):
        job = make_job()
        score = compute_match_score(job, _prefs())
        assert 0.0 <= score <= 1.0

    def test_no_skills_in_description_loses_skill_weight(self):
        job_with = make_job(description="Experience with POS systems and customer service required.")
        job_without = make_job(description="Must be available weekends.")
        prefs = _prefs()
        assert compute_match_score(job_with, prefs) > compute_match_score(job_without, prefs)

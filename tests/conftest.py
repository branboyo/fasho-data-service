from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.models.job import Job


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


def make_job(**overrides) -> Job:
    defaults = {
        "id": 1,
        "company_id": 1,
        "title": "Shift Lead",
        "description": "Looking for a leader with POS systems and customer service experience.",
        "location_text": "San Francisco, CA",
        "pay_min": 18.0,
        "pay_max": 22.0,
        "schedule_type": "full_time",
        "source": "greenhouse",
        "source_url": "https://boards.greenhouse.io/acme/jobs/123",
        "first_seen_at": datetime.now(timezone.utc),
        "posted_at": None,
        "industry": "Retail",
        "dedup_hash": "abc123",
        "raw_payload": {},
    }
    defaults.update(overrides)
    job = Job()
    for k, v in defaults.items():
        setattr(job, k, v)
    return job

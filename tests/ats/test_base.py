import httpx
import pytest

from app.ats.base import ATSClient
from app.schemas.job import RawJob


class FakeClient(ATSClient):
    async def fetch_jobs(self) -> list[RawJob]:
        return [
            RawJob(
                external_id="1",
                title="Barista",
                apply_url="https://example.com/jobs/1",
                raw_payload={"id": 1},
            )
        ]


async def test_ats_client_contract():
    async with httpx.AsyncClient() as http:
        client = FakeClient(http_client=http, config={})
        jobs = await client.fetch_jobs()
    assert len(jobs) == 1
    assert jobs[0].title == "Barista"
    assert jobs[0].description is None


def test_raw_job_rejects_missing_required_fields():
    with pytest.raises(Exception):
        RawJob(title="Barista")  # missing external_id, apply_url, raw_payload

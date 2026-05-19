import json
from pathlib import Path

import httpx
import respx

from app.ats.greenhouse import GreenhouseClient

FIXTURES = Path(__file__).parent.parent / "fixtures"


@respx.mock
async def test_fetch_jobs_parses_greenhouse_response():
    fixture = json.loads((FIXTURES / "greenhouse_jobs.json").read_text())
    respx.get("https://boards-api.greenhouse.io/v1/boards/acmecorp/jobs").mock(
        return_value=httpx.Response(200, json=fixture)
    )

    async with httpx.AsyncClient() as http:
        client = GreenhouseClient(http_client=http, config={"board_token": "acmecorp"})
        jobs = await client.fetch_jobs()

    assert len(jobs) == 2

    lead = jobs[0]
    assert lead.external_id == "4567890"
    assert lead.title == "Shift Lead"
    assert lead.location_raw == "San Francisco, CA"
    assert lead.apply_url == "https://boards.greenhouse.io/acmecorp/jobs/4567890"
    assert lead.schedule_raw == "Full-time"
    assert "Shift Lead" in lead.raw_payload["title"]

    cashier = jobs[1]
    assert cashier.description is None
    assert cashier.schedule_raw is None


@respx.mock
async def test_fetch_jobs_returns_empty_for_no_jobs():
    respx.get("https://boards-api.greenhouse.io/v1/boards/empty/jobs").mock(
        return_value=httpx.Response(200, json={"jobs": []})
    )

    async with httpx.AsyncClient() as http:
        client = GreenhouseClient(http_client=http, config={"board_token": "empty"})
        jobs = await client.fetch_jobs()

    assert jobs == []

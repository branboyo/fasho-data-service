import json
from pathlib import Path

import httpx
import respx

from app.ats.workday import WorkdayClient

FIXTURES = Path(__file__).parent.parent / "fixtures"
WORKDAY_CONFIG = {"tenant": "megahealth", "wd_number": 5, "site": "External"}


@respx.mock
async def test_fetch_jobs_parses_workday_response():
    fixture = json.loads((FIXTURES / "workday_jobs.json").read_text())
    url = "https://megahealth.wd5.myworkdayjobs.com/wday/cxs/megahealth/External/jobs"
    respx.post(url).mock(return_value=httpx.Response(200, json=fixture))

    async with httpx.AsyncClient() as http:
        client = WorkdayClient(http_client=http, config=WORKDAY_CONFIG)
        jobs = await client.fetch_jobs()

    assert len(jobs) == 2

    nurse = jobs[0]
    assert nurse.external_id == "R-12345"
    assert nurse.title == "Registered Nurse - ICU"
    assert nurse.location_raw == "Chicago, IL"
    assert nurse.schedule_raw == "Full time"
    assert "megahealth.wd5.myworkdayjobs.com" in nurse.apply_url

    tech = jobs[1]
    assert tech.schedule_raw == "Part time"
    assert tech.location_raw == "Evanston, IL"


@respx.mock
async def test_fetch_jobs_paginates():
    url = "https://megahealth.wd5.myworkdayjobs.com/wday/cxs/megahealth/External/jobs"
    page1 = {
        "total": 25,
        "jobPostings": [
            {
                "title": f"Job {i}",
                "bulletFields": [f"R-{i}"],
                "locationsText": "Chicago, IL",
                "postedOn": "Posted Today",
                "externalPath": f"/job/{i}/R-{i}",
                "timeType": "Full time",
            }
            for i in range(20)
        ],
    }
    page2 = {
        "total": 25,
        "jobPostings": [
            {
                "title": f"Job {i}",
                "bulletFields": [f"R-{i}"],
                "locationsText": "Chicago, IL",
                "postedOn": "Posted Today",
                "externalPath": f"/job/{i}/R-{i}",
                "timeType": "Full time",
            }
            for i in range(20, 25)
        ],
    }

    route = respx.post(url)
    route.side_effect = [
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
    ]

    async with httpx.AsyncClient() as http:
        client = WorkdayClient(http_client=http, config=WORKDAY_CONFIG)
        jobs = await client.fetch_jobs()

    assert len(jobs) == 25

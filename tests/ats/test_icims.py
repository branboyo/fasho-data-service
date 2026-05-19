from pathlib import Path

import httpx
import respx

from app.ats.icims import ICIMSClient

FIXTURES = Path(__file__).parent.parent / "fixtures"
ICIMS_CONFIG = {"company_slug": "walgreens", "page_size": 50}


@respx.mock
async def test_fetch_jobs_parses_icims_html():
    html = (FIXTURES / "icims_page.html").read_text()
    url = "https://careers-walgreens.icims.com/jobs/search"
    respx.get(url).mock(return_value=httpx.Response(200, text=html))

    async with httpx.AsyncClient() as http:
        client = ICIMSClient(http_client=http, config=ICIMS_CONFIG)
        jobs = await client.fetch_jobs()

    assert len(jobs) == 2

    pharma = jobs[0]
    assert pharma.external_id == "12345"
    assert pharma.title == "Pharmacy Technician"
    assert pharma.location_raw == "Boston, MA"
    assert pharma.schedule_raw == "Full-Time"
    assert "12345" in pharma.apply_url

    lead = jobs[1]
    assert lead.external_id == "12346"
    assert lead.title == "Shift Lead"


@respx.mock
async def test_fetch_jobs_handles_empty_page():
    html = """
    <html><body>
    <div class="iCIMS_JobsTable"></div>
    <div class="iCIMS_Paginator"><span class="iCIMS_PgCount">Page 1 of 1</span></div>
    </body></html>
    """
    url = "https://careers-walgreens.icims.com/jobs/search"
    respx.get(url).mock(return_value=httpx.Response(200, text=html))

    async with httpx.AsyncClient() as http:
        client = ICIMSClient(http_client=http, config=ICIMS_CONFIG)
        jobs = await client.fetch_jobs()

    assert jobs == []

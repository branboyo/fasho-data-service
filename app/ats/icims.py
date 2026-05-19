import re

from bs4 import BeautifulSoup

from app.ats.base import ATSClient
from app.schemas.job import RawJob


class ICIMSClient(ATSClient):
    async def fetch_jobs(self) -> list[RawJob]:
        slug = self.config["company_slug"]
        page_size = self.config.get("page_size", 50)
        url = f"https://careers-{slug}.icims.com/jobs/search"

        all_jobs: list[RawJob] = []
        page = 1

        while True:
            resp = await self.http.get(
                url,
                params={
                    "ss": 1,
                    "searchRelation": "keyword_all",
                    "in_iframe": 1,
                    "iCIMS_PageSize": page_size,
                    "iCIMS_Page": page,
                },
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            rows = soup.select("div.iCIMS_JobsTable div.row[data-job-id]")
            for row in rows:
                all_jobs.append(self._parse_row(row))

            if not self._has_next_page(soup, page):
                break
            page += 1

        return all_jobs

    def _parse_row(self, row) -> RawJob:
        job_id = row.get("data-job-id", "unknown")
        title_tag = row.select_one("span.title")
        title = title_tag.get_text(strip=True) if title_tag else "Unknown"
        link_tag = row.select_one("a.iCIMS_Anchor")
        apply_url = link_tag["href"] if link_tag and link_tag.has_attr("href") else ""
        location_tag = row.select_one("span.location")
        location = location_tag.get_text(strip=True) if location_tag else None
        date_tag = row.select_one("span.date")
        posted = date_tag.get_text(strip=True) if date_tag else None
        type_tag = row.select_one("span.type")
        schedule = type_tag.get_text(strip=True) if type_tag else None

        return RawJob(
            external_id=job_id,
            title=title,
            location_raw=location,
            schedule_raw=schedule,
            posted_at=posted,
            apply_url=apply_url,
            raw_payload={"job_id": job_id, "title": title, "location": location},
        )

    def _has_next_page(self, soup: BeautifulSoup, current_page: int) -> bool:
        pg = soup.select_one("span.iCIMS_PgCount")
        if not pg:
            return False
        match = re.search(r"Page\s+(\d+)\s+of\s+(\d+)", pg.get_text())
        if not match:
            return False
        return current_page < int(match.group(2))

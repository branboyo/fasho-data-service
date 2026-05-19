import re

import httpx

from app.ats.base import ATSClient
from app.schemas.job import RawJob

PAGE_SIZE = 20


class WorkdayClient(ATSClient):
    def _base_url(self) -> str:
        t = self.config["tenant"]
        n = self.config["wd_number"]
        s = self.config["site"]
        return f"https://{t}.wd{n}.myworkdayjobs.com/wday/cxs/{t}/{s}/jobs"

    async def fetch_jobs(self) -> list[RawJob]:
        all_jobs: list[RawJob] = []
        offset = 0

        while True:
            resp = await self.http.post(
                self._base_url(),
                json={"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": ""},
            )
            resp.raise_for_status()
            data = resp.json()

            for posting in data.get("jobPostings", []):
                all_jobs.append(self._parse(posting))

            if offset + PAGE_SIZE >= data.get("total", 0):
                break
            offset += PAGE_SIZE

        return all_jobs

    def _parse(self, raw: dict) -> RawJob:
        external_id = self._extract_req_id(raw.get("bulletFields", []))
        path = raw.get("externalPath", "")
        t = self.config["tenant"]
        n = self.config["wd_number"]
        s = self.config["site"]
        apply_url = f"https://{t}.wd{n}.myworkdayjobs.com/{s}{path}"

        return RawJob(
            external_id=external_id,
            title=raw["title"],
            location_raw=raw.get("locationsText"),
            schedule_raw=raw.get("timeType"),
            posted_at=raw.get("postedOn"),
            apply_url=apply_url,
            raw_payload=raw,
        )

    def _extract_req_id(self, bullet_fields: list[str]) -> str:
        for field in bullet_fields:
            if re.match(r"R-\d+", field):
                return field
        return bullet_fields[0] if bullet_fields else "unknown"

import httpx

from app.ats.base import ATSClient
from app.schemas.job import RawJob


class GreenhouseClient(ATSClient):
    BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

    async def fetch_jobs(self) -> list[RawJob]:
        board_token = self.config["board_token"]
        url = f"{self.BASE_URL}/{board_token}/jobs"
        resp = await self.http.get(url, params={"content": "true"})
        resp.raise_for_status()
        return [self._parse(j) for j in resp.json()["jobs"]]

    def _parse(self, raw: dict) -> RawJob:
        schedule = None
        for m in raw.get("metadata", []):
            if m.get("name") == "Employment Type":
                schedule = m.get("value")
                break

        return RawJob(
            external_id=str(raw["id"]),
            title=raw["title"],
            description=raw.get("content"),
            location_raw=raw.get("location", {}).get("name"),
            schedule_raw=schedule,
            posted_at=raw.get("updated_at"),
            apply_url=raw["absolute_url"],
            raw_payload=raw,
        )

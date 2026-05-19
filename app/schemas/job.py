from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RawJob(BaseModel):
    external_id: str
    title: str
    description: str | None = None
    location_raw: str | None = None
    pay_min: float | None = None
    pay_max: float | None = None
    schedule_raw: str | None = None
    posted_at: str | None = None
    apply_url: str
    raw_payload: dict


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    title: str
    description: str | None
    location_text: str | None
    pay_min: float | None
    pay_max: float | None
    schedule_type: str | None
    source: str
    source_url: str
    first_seen_at: datetime
    posted_at: datetime | None
    industry: str | None

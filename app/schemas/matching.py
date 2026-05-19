from pydantic import BaseModel, ConfigDict


class MatchRequest(BaseModel):
    latitude: float
    longitude: float
    commute_radius_m: float = 40000.0
    industries: list[str]
    schedules: list[str] = []
    pay_floor: float = 0.0
    hard_skills: list[str] = []
    soft_skills: list[str] = []


class JobMatch(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    title: str
    description: str | None
    location_text: str | None
    pay_min: float | None
    pay_max: float | None
    schedule_type: str | None
    source_url: str
    industry: str | None
    score: float

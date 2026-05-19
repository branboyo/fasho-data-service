from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None]
    location_geo = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    location_text: Mapped[str | None] = mapped_column(String(255))
    pay_min: Mapped[float | None] = mapped_column(Numeric(10, 2))
    pay_max: Mapped[float | None] = mapped_column(Numeric(10, 2))
    schedule_type: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(50))
    source_url: Mapped[str] = mapped_column(String(2048))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    industry: Mapped[str | None] = mapped_column(String(100))
    dedup_hash: Mapped[str] = mapped_column(String(64), index=True)

    company: Mapped["Company"] = relationship(back_populates="jobs")

    __table_args__ = (
        Index("ix_jobs_feed", "industry", "schedule_type", first_seen_at.desc()),
    )

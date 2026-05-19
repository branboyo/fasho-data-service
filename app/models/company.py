import enum

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


from app.models.base import Base


class ATSType(str, enum.Enum):
    GREENHOUSE = "greenhouse"
    WORKDAY = "workday"
    ICIMS = "icims"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    domain: Mapped[str | None] = mapped_column(String(255))
    ats_type: Mapped[ATSType]
    ats_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    industry: Mapped[str | None] = mapped_column(String(100))

    jobs: Mapped[list["Job"]] = relationship(back_populates="company")

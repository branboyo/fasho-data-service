from unittest.mock import AsyncMock, patch

from app.schemas.job import RawJob
from app.services.ingest import IngestResult, IngestService, parse_posted_at, parse_schedule


def _raw_job(**overrides) -> RawJob:
    defaults = dict(
        external_id="1",
        title="Shift Lead",
        description="Lead the shift.",
        location_raw="San Francisco, CA",
        pay_min=18.0,
        pay_max=22.0,
        schedule_raw="Full-time",
        posted_at="2026-05-15T10:00:00Z",
        apply_url="https://example.com/jobs/1",
        raw_payload={"id": 1},
    )
    defaults.update(overrides)
    return RawJob(**defaults)


class TestParseHelpers:
    def test_parse_schedule_full_time_variants(self):
        assert parse_schedule("Full-time") == "full_time"
        assert parse_schedule("Full time") == "full_time"
        assert parse_schedule("FT") == "full_time"

    def test_parse_schedule_part_time_variants(self):
        assert parse_schedule("Part-Time") == "part_time"
        assert parse_schedule("Part time") == "part_time"

    def test_parse_schedule_unknown_returns_none(self):
        assert parse_schedule("Contract") is None
        assert parse_schedule(None) is None

    def test_parse_posted_at_iso_format(self):
        result = parse_posted_at("2026-05-15T10:00:00-05:00")
        assert result is not None
        assert result.day == 15

    def test_parse_posted_at_human_date(self):
        result = parse_posted_at("May 14, 2026")
        assert result is not None
        assert result.month == 5

    def test_parse_posted_at_relative_returns_none(self):
        assert parse_posted_at("Posted 2 Days Ago") is None

    def test_parse_posted_at_none_returns_none(self):
        assert parse_posted_at(None) is None


class TestIngestService:
    async def test_stores_new_job(self, mock_session):
        geocoder = AsyncMock()
        geocoder.geocode.return_value = (37.7749, -122.4194)
        service = IngestService(geocoder=geocoder)

        with patch("app.services.ingest.is_duplicate", return_value=False):
            result = await service.ingest_jobs(
                company_id=1,
                source="greenhouse",
                industry="Retail",
                raw_jobs=[_raw_job()],
                session=mock_session,
            )

        assert result.stored == 1
        assert result.skipped == 0
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    async def test_skips_duplicate_job(self, mock_session):
        geocoder = AsyncMock()
        service = IngestService(geocoder=geocoder)

        with patch("app.services.ingest.is_duplicate", return_value=True):
            result = await service.ingest_jobs(
                company_id=1,
                source="greenhouse",
                industry="Retail",
                raw_jobs=[_raw_job()],
                session=mock_session,
            )

        assert result.stored == 0
        assert result.skipped == 1
        mock_session.add.assert_not_called()

    async def test_handles_geocode_failure_gracefully(self, mock_session):
        geocoder = AsyncMock()
        geocoder.geocode.return_value = None
        service = IngestService(geocoder=geocoder)

        with patch("app.services.ingest.is_duplicate", return_value=False):
            result = await service.ingest_jobs(
                company_id=1,
                source="greenhouse",
                industry="Retail",
                raw_jobs=[_raw_job()],
                session=mock_session,
            )

        assert result.stored == 1
        added_job = mock_session.add.call_args[0][0]
        assert added_job.location_geo is None
        assert added_job.location_text == "San Francisco, CA"

    async def test_normalizes_schedule_type(self, mock_session):
        geocoder = AsyncMock()
        geocoder.geocode.return_value = None
        service = IngestService(geocoder=geocoder)

        with patch("app.services.ingest.is_duplicate", return_value=False):
            await service.ingest_jobs(
                company_id=1,
                source="greenhouse",
                industry="Retail",
                raw_jobs=[_raw_job(schedule_raw="Part-Time")],
                session=mock_session,
            )

        added_job = mock_session.add.call_args[0][0]
        assert added_job.schedule_type == "part_time"

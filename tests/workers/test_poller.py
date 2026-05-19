from unittest.mock import AsyncMock, MagicMock, patch

from app.models.company import ATSType, Company
from app.workers.poller import poll_company


def _company(**overrides) -> Company:
    c = Company()
    defaults = {
        "id": 1,
        "name": "Acme Corp",
        "ats_type": ATSType.GREENHOUSE,
        "ats_config": {"board_token": "acme"},
        "industry": "Retail",
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(c, k, v)
    return c


async def test_poll_company_fetches_and_ingests():
    company = _company()
    mock_session = AsyncMock()
    mock_session.get.return_value = company

    mock_client = AsyncMock()
    mock_client.fetch_jobs.return_value = []

    mock_ingest = AsyncMock()
    mock_ingest.ingest_jobs.return_value = MagicMock(stored=0, skipped=0)

    with (
        patch("app.workers.poller.async_session") as mock_session_factory,
        patch("app.workers.poller.get_client", return_value=mock_client),
        patch("app.workers.poller.IngestService", return_value=mock_ingest),
    ):
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await poll_company({"redis": AsyncMock()}, company.id)

    mock_session.get.assert_awaited_once_with(Company, 1)
    mock_client.fetch_jobs.assert_awaited_once()
    mock_ingest.ingest_jobs.assert_awaited_once()


async def test_poll_company_skips_missing_company():
    mock_session = AsyncMock()
    mock_session.get.return_value = None

    with patch("app.workers.poller.async_session") as mock_session_factory:
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await poll_company({"redis": AsyncMock()}, 999)

    assert result is None

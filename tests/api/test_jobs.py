from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/api/v1/jobs/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_match_endpoint_validates_input():
    resp = client.post("/api/v1/jobs/match", json={})
    assert resp.status_code == 422


def test_match_endpoint_returns_scored_jobs():
    from tests.conftest import make_job
    from app.database import get_session

    mock_job = make_job()

    async def mock_get_session():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_job]
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_session] = mock_get_session
    try:
        resp = client.post(
            "/api/v1/jobs/match",
            json={
                "latitude": 37.77,
                "longitude": -122.42,
                "industries": ["Retail"],
                "schedules": ["full_time"],
                "pay_floor": 17.0,
                "hard_skills": ["POS systems"],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert "score" in data[0]
    assert data[0]["title"] == "Shift Lead"

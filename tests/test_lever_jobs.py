import httpx
import respx
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from app.services.job_collection.lever_jobs import (
    LEVER_API_URL,
    RateLimiter,
    export_results,
    fetch_all_jobs,
    fetch_jobs_for_token,
    fetch_lever_tokens,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_supabase(tokens: list[str]) -> MagicMock:
    """Return a mock Supabase client that yields the given tokens."""
    client = MagicMock()
    execute_result = MagicMock()
    execute_result.data = [{"token": t} for t in tokens]
    (
        client.table.return_value
        .select.return_value
        .eq.return_value
        .limit.return_value
        .execute
    ).return_value = execute_result
    return client


def _lever_posting(title: str = "Software Engineer", token: str = "acme") -> dict:
    return {
        "id": "abc-123",
        "text": title,
        "hostedUrl": f"https://jobs.lever.co/{token}/abc-123",
        "applyUrl": f"https://jobs.lever.co/{token}/abc-123/apply",
        "categories": {
            "commitment": "Full-time",
            "department": "Engineering",
            "location": "San Francisco, CA",
            "team": "Backend",
            "allLocations": ["San Francisco, CA", "New York, NY"],
        },
        "createdAt": 1700000000000,
        "workplaceType": "remote",
        "descriptionPlain": "Build and ship features.",
        "additional": "Competitive salary.",
        "lists": [
            {"text": "Requirements", "content": "3+ years experience\nPython proficiency"},
        ],
    }


# ── fetch_lever_tokens ───────────────────────────────────────────────────────


class TestFetchLeverTokens:
    def test_returns_token_strings(self):
        client = _mock_supabase(["acme", "beta"])
        tokens = fetch_lever_tokens(client, limit=10)
        assert tokens == ["acme", "beta"]

    def test_queries_correct_table_and_filter(self):
        client = _mock_supabase([])
        fetch_lever_tokens(client, limit=5)

        client.table.assert_called_once_with("tokens")
        client.table.return_value.select.assert_called_once_with("token")
        client.table.return_value.select.return_value.eq.assert_called_once_with("ats", "lever")
        client.table.return_value.select.return_value.eq.return_value.limit.assert_called_once_with(5)

    def test_empty_table(self):
        client = _mock_supabase([])
        assert fetch_lever_tokens(client) == []


# ── fetch_jobs_for_token ──────────────────────────────────────────────────────


class TestFetchJobsForToken:
    @respx.mock
    async def test_returns_postings(self):
        posting = _lever_posting("SWE", "acme")
        respx.get(f"{LEVER_API_URL}/acme").mock(
            return_value=httpx.Response(200, json=[posting])
        )

        async with httpx.AsyncClient() as client:
            jobs = await fetch_jobs_for_token(client, "acme", RateLimiter())

        assert len(jobs) == 1
        assert jobs[0]["text"] == "SWE"

    @respx.mock
    async def test_empty_postings(self):
        respx.get(f"{LEVER_API_URL}/ghost").mock(
            return_value=httpx.Response(200, json=[])
        )

        async with httpx.AsyncClient() as client:
            jobs = await fetch_jobs_for_token(client, "ghost", RateLimiter())

        assert jobs == []


# ── fetch_all_jobs ────────────────────────────────────────────────────────────


class TestFetchAllJobs:
    @respx.mock
    async def test_fetches_jobs_for_each_token(self):
        respx.get(f"{LEVER_API_URL}/acme").mock(
            return_value=httpx.Response(200, json=[_lever_posting("SWE", "acme")])
        )
        respx.get(f"{LEVER_API_URL}/beta").mock(
            return_value=httpx.Response(200, json=[
                _lever_posting("PM", "beta"),
                _lever_posting("Designer", "beta"),
            ])
        )

        client = _mock_supabase(["acme", "beta"])
        results = await fetch_all_jobs(client)

        assert len(results) == 2
        assert len(results["acme"]) == 1
        assert len(results["beta"]) == 2

    @respx.mock
    async def test_handles_api_errors_gracefully(self):
        respx.get(f"{LEVER_API_URL}/acme").mock(
            return_value=httpx.Response(200, json=[_lever_posting()])
        )
        respx.get(f"{LEVER_API_URL}/gone").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )

        client = _mock_supabase(["acme", "gone"])
        results = await fetch_all_jobs(client)

        assert len(results["acme"]) == 1
        assert results["gone"] == []

    async def test_no_tokens_returns_empty(self):
        client = _mock_supabase([])
        results = await fetch_all_jobs(client)
        assert results == {}


# ── export_results ────────────────────────────────────────────────────────────


class TestExportResults:
    def test_writes_file_with_job_details(self):
        results = {
            "acme": [_lever_posting("SWE", "acme")],
            "beta": [_lever_posting("PM", "beta"), _lever_posting("Designer", "beta")],
        }

        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test_output.txt"
            export_results(results, output)

            content = output.read_text()
            assert "acme (1 job)" in content
            assert "beta (2 jobs)" in content
            assert "SWE" in content
            assert "PM" in content
            assert "Designer" in content
            assert "San Francisco, CA" in content
            assert "New York, NY" in content
            assert "Engineering" in content
            assert "remote" in content
            assert "abc-123" in content
            assert "2023-11-14" in content
            assert "Build and ship features." in content
            assert "Competitive salary." in content
            assert "Requirements:" in content
            assert "3+ years experience" in content
            assert "Python proficiency" in content
            assert "/apply" in content
            assert "Companies: 2" in content
            assert "Jobs: 3" in content

    def test_handles_empty_results(self):
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "empty.txt"
            export_results({"ghost": []}, output)

            content = output.read_text()
            assert "(No listings found)" in content
            assert "Jobs: 0" in content

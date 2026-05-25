from unittest.mock import MagicMock

from app.services.token_collection.brave_search import LeverListing
from app.services.token_collection.supabase_upload import upsert_listings, upload_all_terms

TABLE = "tokens"


def _mock_client(return_data: list[dict] | None = None) -> MagicMock:
    """Return a mock Supabase client with a preconfigured upsert chain."""
    client = MagicMock()
    execute_result = MagicMock()
    execute_result.data = return_data or []
    client.table.return_value.upsert.return_value.execute.return_value = execute_result
    return client


def _listing(token: str, query: str = "tech") -> LeverListing:
    return LeverListing(
        url=f"https://jobs.lever.co/{token}/",
        company_name=f"Company {token}",
        origin_query=query,
        ats="lever",
        token=token,
    )


class TestUpsertListings:
    def test_upserts_with_on_conflict_url(self):
        client = _mock_client([{"token": "acme"}])
        upsert_listings(client, [_listing("acme")])

        client.table.assert_called_once_with(TABLE)
        call_args = client.table.return_value.upsert.call_args
        assert call_args[0][0] == [
            {
                "url": "https://jobs.lever.co/acme/",
                "company_name": "Company acme",
                "origin_query": "tech",
                "ats": "lever",
                "token": "acme",
            }
        ]
        assert call_args[1]["on_conflict"] == "url"

    def test_no_op_for_empty_list(self):
        client = _mock_client()
        assert upsert_listings(client, []) == []
        client.table.assert_not_called()

    def test_returns_response_data(self):
        expected = [{"token": "acme"}, {"token": "beta"}]
        client = _mock_client(expected)
        assert upsert_listings(client, [_listing("acme"), _listing("beta")]) == expected


class TestUploadAllTerms:
    def test_deduplicates_across_terms(self):
        client = _mock_client([{"token": "acme"}])
        results = {
            "software engineer": [_listing("acme", "software engineer")],
            "data engineer": [_listing("acme", "data engineer"), _listing("beta", "data engineer")],
        }

        upload_all_terms(client, results)

        rows = client.table.return_value.upsert.call_args[0][0]
        assert [r["token"] for r in rows] == ["acme", "beta"]

    def test_empty_results(self):
        client = _mock_client()
        assert upload_all_terms(client, {}) == []

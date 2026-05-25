import httpx
import pytest
import respx

from app.services.token_collection.brave_search import (
    BRAVE_SEARCH_URL,
    LeverListing,
    QueryRotator,
    SearchConfig,
    _sanitize_company_name,
    _sanitize_lever_url,
    fetch_all_terms,
    sanitize_results,
    search_jobs,
)

API_KEY = "test-key"


def _brave_response(results: list[dict]) -> dict:
    return {
        "query": {"original": "test"},
        "web": {"results": results},
    }


# ── QueryRotator ──────────────────────────────────────────────────────────────


class TestQueryRotator:
    def test_query_format(self):
        r = QueryRotator(site="jobs.lever.co", terms=["software engineer"])
        assert r.next() == "site:jobs.lever.co software engineer"

    def test_cycles_through_terms(self):
        r = QueryRotator(site="jobs.lever.co", terms=["a", "b", "c"])
        assert r.next() == "site:jobs.lever.co a"
        assert r.next() == "site:jobs.lever.co b"
        assert r.next() == "site:jobs.lever.co c"
        assert r.next() == "site:jobs.lever.co a"

    def test_reset(self):
        r = QueryRotator(site="jobs.lever.co", terms=["x", "y"])
        r.next()
        r.next()
        r.reset()
        assert r.next() == "site:jobs.lever.co x"

    def test_current_index(self):
        r = QueryRotator(site="jobs.lever.co", terms=["a", "b", "c"])
        assert r.current_index == 0
        r.next()
        assert r.current_index == 1
        r.next()
        r.next()
        assert r.current_index == 0

    @respx.mock
    async def test_query_reaches_api_verbatim(self):
        route = respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(200, json=_brave_response([]))
        )
        rotator = QueryRotator(site="jobs.lever.co", terms=["software engineer"])
        await search_jobs(API_KEY, rotator)

        url = str(route.calls.last.request.url)
        assert "q=site%3Ajobs.lever.co+software+engineer" in url


# ── URL sanitization ─────────────────────────────────────────────────────────


class TestSanitizeLeverUrl:
    def test_strips_job_id(self):
        url, token = _sanitize_lever_url("https://jobs.lever.co/skywarditsolutions/abc-123")
        assert url == "https://jobs.lever.co/skywarditsolutions/"
        assert token == "skywarditsolutions"

    def test_already_clean(self):
        url, token = _sanitize_lever_url("https://jobs.lever.co/skywarditsolutions/")
        assert url == "https://jobs.lever.co/skywarditsolutions/"
        assert token == "skywarditsolutions"

    def test_no_trailing_slash(self):
        url, token = _sanitize_lever_url("https://jobs.lever.co/acme")
        assert url == "https://jobs.lever.co/acme/"
        assert token == "acme"

    def test_deeply_nested_path(self):
        url, token = _sanitize_lever_url("https://jobs.lever.co/company/job-id/apply")
        assert url == "https://jobs.lever.co/company/"
        assert token == "company"

    def test_empty_path(self):
        _, token = _sanitize_lever_url("https://jobs.lever.co/")
        assert token == ""

    def test_bare_domain(self):
        _, token = _sanitize_lever_url("https://jobs.lever.co")
        assert token == ""


# ── Company name sanitization ────────────────────────────────────────────────


class TestSanitizeCompanyName:
    def test_strips_after_dash(self):
        assert _sanitize_company_name("Acme Corp - Software Engineer") == "Acme Corp"

    def test_no_dash_unchanged(self):
        assert _sanitize_company_name("Acme Corp") == "Acme Corp"

    def test_only_first_dash(self):
        assert _sanitize_company_name("Acme - Corp - Engineering") == "Acme"

    def test_trims_whitespace(self):
        assert _sanitize_company_name("  Acme Corp  - Jobs  ") == "Acme Corp"

    def test_hyphenated_name_kept(self):
        assert _sanitize_company_name("Acme-Corp") == "Acme-Corp"

    def test_empty_string(self):
        assert _sanitize_company_name("") == ""


# ── Result sanitization ──────────────────────────────────────────────────────


class TestSanitizeResults:
    def test_transforms_raw_to_listings(self):
        raw = [
            {"title": "SWE at Acme - Lever", "url": "https://jobs.lever.co/acme/123"},
            {"title": "Data at Beta", "url": "https://jobs.lever.co/beta/456"},
        ]
        listings = sanitize_results(raw, "software engineer")
        assert len(listings) == 2
        assert listings[0] == LeverListing(
            url="https://jobs.lever.co/acme/",
            company_name="SWE at Acme",
            origin_query="software engineer",
            ats="lever",
            token="acme",
        )
        assert listings[1].token == "beta"

    def test_deduplicates_by_token(self):
        raw = [
            {"title": "SWE at Acme", "url": "https://jobs.lever.co/acme/123"},
            {"title": "PM at Acme", "url": "https://jobs.lever.co/acme/456"},
        ]
        listings = sanitize_results(raw, "tech")
        assert len(listings) == 1
        assert listings[0].token == "acme"

    def test_skips_empty_token(self):
        assert sanitize_results([{"title": "Bad", "url": "https://jobs.lever.co/"}], "tech") == []

    def test_preserves_origin_query(self):
        raw = [{"title": "Job", "url": "https://jobs.lever.co/co/1"}]
        assert sanitize_results(raw, "machine learning")[0].origin_query == "machine learning"

    def test_ats_is_lever(self):
        raw = [{"title": "Job", "url": "https://jobs.lever.co/co/1"}]
        assert sanitize_results(raw, "tech")[0].ats == "lever"

    def test_filters_non_lever_urls(self):
        raw = [
            {"title": "Lever Job", "url": "https://jobs.lever.co/acme/123"},
            {"title": "Indeed", "url": "https://www.indeed.com/job/456"},
            {"title": "Greenhouse", "url": "https://boards.greenhouse.io/co/789"},
        ]
        listings = sanitize_results(raw, "tech")
        assert len(listings) == 1
        assert listings[0].token == "acme"


# ── SearchConfig ──────────────────────────────────────────────────────────────


class TestSearchConfig:
    def test_clamps_count_and_offset(self):
        params = SearchConfig(count=50, offset=99).to_params("test")
        assert params["count"] == 20
        assert params["offset"] == 9

    def test_includes_freshness_when_set(self):
        assert SearchConfig(freshness="pw").to_params("test")["freshness"] == "pw"

    def test_omits_freshness_when_none(self):
        assert "freshness" not in SearchConfig().to_params("test")

    def test_joins_result_filter(self):
        params = SearchConfig(result_filter=["web", "news"]).to_params("test")
        assert params["result_filter"] == "web,news"

    def test_defaults(self):
        params = SearchConfig().to_params("test")
        assert params["count"] == 20
        assert params["offset"] == 0
        assert params["country"] == "US"
        assert params["safesearch"] == "moderate"
        assert params["operators"] == "true"


# ── search_jobs ───────────────────────────────────────────────────────────────


class TestSearchJobs:
    @respx.mock
    async def test_returns_sanitized_listings(self):
        respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(
                200,
                json=_brave_response([
                    {
                        "title": "Software Engineer at Acme",
                        "url": "https://jobs.lever.co/acme/123-abc",
                        "description": "Build cool stuff",
                    }
                ]),
            )
        )

        rotator = QueryRotator(site="jobs.lever.co", terms=["software engineer"])
        results = await search_jobs(API_KEY, rotator)

        assert len(results) == 1
        assert results[0] == LeverListing(
            url="https://jobs.lever.co/acme/",
            company_name="Software Engineer at Acme",
            origin_query="software engineer",
            ats="lever",
            token="acme",
        )

    @respx.mock
    async def test_forwards_config_to_api(self):
        route = respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(200, json=_brave_response([]))
        )

        rotator = QueryRotator(site="jobs.lever.co", terms=["tech"])
        cfg = SearchConfig(count=10, offset=2, freshness="pw", country="GB")
        await search_jobs(API_KEY, rotator, config=cfg)

        request = route.calls.last.request
        assert request.headers["x-subscription-token"] == API_KEY
        url = str(request.url)
        assert "count=10" in url
        assert "offset=2" in url
        assert "freshness=pw" in url
        assert "country=GB" in url

    @respx.mock
    async def test_empty_results(self):
        respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(200, json=_brave_response([]))
        )
        rotator = QueryRotator(site="jobs.lever.co", terms=["niche role"])
        assert await search_jobs(API_KEY, rotator) == []

    @respx.mock
    async def test_api_error_raises(self):
        respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )
        rotator = QueryRotator(site="jobs.lever.co", terms=["tech"])
        with pytest.raises(httpx.HTTPStatusError):
            await search_jobs(API_KEY, rotator)


# ── fetch_all_terms ───────────────────────────────────────────────────────────


class TestFetchAllTerms:
    @respx.mock
    async def test_paginates_with_offsets(self):
        route = respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(
                200,
                json=_brave_response([
                    {"title": f"Job {i}", "url": f"https://jobs.lever.co/co{i}/{i}"}
                    for i in range(20)
                ]),
            )
        )

        rotator = QueryRotator(site="jobs.lever.co", terms=["tech"])
        await fetch_all_terms(API_KEY, rotator, results_per_term=100)

        assert route.call_count == 5
        offsets = [
            str(c.request.url).split("offset=")[1].split("&")[0]
            for c in route.calls
        ]
        assert offsets == ["0", "1", "2", "3", "4"]

    @respx.mock
    async def test_stops_early_on_incomplete_page(self):
        route = respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(
                200,
                json=_brave_response([
                    {"title": "Job", "url": "https://jobs.lever.co/only/1"}
                ]),
            )
        )

        rotator = QueryRotator(site="jobs.lever.co", terms=["tech"])
        await fetch_all_terms(API_KEY, rotator, results_per_term=100)

        assert route.call_count == 1

    @respx.mock
    async def test_defaults_freshness_to_pw(self):
        route = respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(200, json=_brave_response([]))
        )

        rotator = QueryRotator(site="jobs.lever.co", terms=["tech"])
        await fetch_all_terms(API_KEY, rotator)

        assert "freshness=pw" in str(route.calls.last.request.url)

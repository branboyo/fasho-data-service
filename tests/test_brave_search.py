import httpx
import pytest
import respx

from app.services.token_collection.brave_search import (
    ASHBYHQ_DOMAIN,
    BRAVE_SEARCH_URL,
    LEVER_DOMAIN,
    LeverListing,
    QueryRotator,
    SearchConfig,
    _extract_token,
    _sanitize_company_name,
    fetch_all_terms,
    sanitize_results,
    search_jobs,
)

API_KEY = "test-key"


def _brave_response(results: list[dict]) -> dict:
    return {"query": {"original": "test"}, "web": {"results": results}}


# ── QueryRotator ──────────────────────────────────────────────────────────────


class TestQueryRotator:
    def test_single_site_query_format(self):
        r = QueryRotator(sites=["jobs.lever.co"], terms=["software engineer"])
        assert r.next() == "site:jobs.lever.co software engineer"

    def test_exhausts_all_terms_for_first_site_before_second(self):
        r = QueryRotator(sites=["jobs.lever.co", "ashbyhq.com"], terms=["a", "b"])
        assert r.next() == "site:jobs.lever.co a"
        assert r.next() == "site:jobs.lever.co b"
        assert r.next() == "site:ashbyhq.com a"
        assert r.next() == "site:ashbyhq.com b"
        # wraps back to start
        assert r.next() == "site:jobs.lever.co a"

    def test_total_reflects_sites_times_terms(self):
        r = QueryRotator(sites=["a.com", "b.com", "c.com"], terms=["x", "y"])
        assert r.total == 6

    def test_reset_returns_to_first_site_first_term(self):
        r = QueryRotator(sites=["jobs.lever.co", "ashbyhq.com"], terms=["x", "y"])
        for _ in range(4):
            r.next()
        r.reset()
        assert r.next() == "site:jobs.lever.co x"

    def test_current_index_tracks_position_in_full_cycle(self):
        r = QueryRotator(sites=["a.com", "b.com"], terms=["1", "2"])
        assert r.current_index == 0
        r.next()
        assert r.current_index == 1
        r.next()
        assert r.current_index == 2
        r.next()
        assert r.current_index == 3
        r.next()
        assert r.current_index == 0  # wrapped

    @respx.mock
    async def test_query_reaches_api_verbatim(self):
        route = respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(200, json=_brave_response([]))
        )
        rotator = QueryRotator(sites=["jobs.lever.co"], terms=["software engineer"])
        await search_jobs(API_KEY, rotator)

        url = str(route.calls.last.request.url)
        assert "q=site%3Ajobs.lever.co+software+engineer" in url


# ── URL / token extraction ───────────────────────────────────────────────────


class TestExtractToken:
    def test_lever_strips_job_id(self):
        url, token = _extract_token("https://jobs.lever.co/acme/abc-123", LEVER_DOMAIN)
        assert url == "https://jobs.lever.co/acme/"
        assert token == "acme"

    def test_ashby_strips_job_id(self):
        url, token = _extract_token("https://jobs.ashbyhq.com/acme/abc-123", ASHBYHQ_DOMAIN)
        assert url == "https://jobs.ashbyhq.com/acme/"
        assert token == "acme"

    def test_already_clean(self):
        url, token = _extract_token("https://jobs.lever.co/acme/", LEVER_DOMAIN)
        assert url == "https://jobs.lever.co/acme/"
        assert token == "acme"

    def test_deeply_nested_path(self):
        url, token = _extract_token("https://jobs.lever.co/company/job/apply", LEVER_DOMAIN)
        assert url == "https://jobs.lever.co/company/"
        assert token == "company"

    def test_empty_path_returns_empty_token(self):
        _, token = _extract_token("https://jobs.lever.co/", LEVER_DOMAIN)
        assert token == ""

    def test_bare_domain_returns_empty_token(self):
        _, token = _extract_token("https://jobs.lever.co", LEVER_DOMAIN)
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

    def test_hyphenated_name_unchanged(self):
        assert _sanitize_company_name("Acme-Corp") == "Acme-Corp"

    def test_empty_string(self):
        assert _sanitize_company_name("") == ""


# ── sanitize_results ─────────────────────────────────────────────────────────


class TestSanitizeResults:
    def test_lever_ats_label(self):
        raw = [{"title": "Job", "url": "https://jobs.lever.co/co/1"}]
        assert sanitize_results(raw, "tech", LEVER_DOMAIN)[0].ats == "lever"

    def test_ashby_ats_label(self):
        raw = [{"title": "Job", "url": "https://jobs.ashbyhq.com/co/1"}]
        assert sanitize_results(raw, "tech", ASHBYHQ_DOMAIN)[0].ats == "ashbyhq"

    def test_deduplicates_by_token(self):
        raw = [
            {"title": "SWE", "url": "https://jobs.lever.co/acme/1"},
            {"title": "PM",  "url": "https://jobs.lever.co/acme/2"},
        ]
        assert len(sanitize_results(raw, "tech", LEVER_DOMAIN)) == 1

    def test_filters_out_non_matching_site(self):
        raw = [
            {"title": "Lever",      "url": "https://jobs.lever.co/acme/1"},
            {"title": "Indeed",     "url": "https://www.indeed.com/job/456"},
            {"title": "Greenhouse", "url": "https://boards.greenhouse.io/co/789"},
        ]
        results = sanitize_results(raw, "tech", LEVER_DOMAIN)
        assert len(results) == 1
        assert results[0].token == "acme"

    def test_filters_lever_when_searching_ashby(self):
        raw = [
            {"title": "Lever Job", "url": "https://jobs.lever.co/acme/1"},
            {"title": "Ashby Job", "url": "https://jobs.ashbyhq.com/acme/1"},
        ]
        results = sanitize_results(raw, "tech", ASHBYHQ_DOMAIN)
        assert len(results) == 1
        assert "ashbyhq" in results[0].url

    def test_skips_empty_token(self):
        assert sanitize_results([{"title": "Bad", "url": "https://jobs.lever.co/"}], "tech", LEVER_DOMAIN) == []

    def test_preserves_origin_query(self):
        raw = [{"title": "Job", "url": "https://jobs.lever.co/co/1"}]
        assert sanitize_results(raw, "machine learning", LEVER_DOMAIN)[0].origin_query == "machine learning"

    def test_transforms_raw_to_listing(self):
        raw = [{"title": "SWE at Acme - Lever", "url": "https://jobs.lever.co/acme/123"}]
        listing = sanitize_results(raw, "software engineer", LEVER_DOMAIN)[0]
        assert listing == LeverListing(
            url="https://jobs.lever.co/acme/",
            company_name="SWE at Acme",
            origin_query="software engineer",
            ats="lever",
            token="acme",
        )


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
        assert SearchConfig(result_filter=["web", "news"]).to_params("test")["result_filter"] == "web,news"

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
            return_value=httpx.Response(200, json=_brave_response([
                {"title": "SWE at Acme", "url": "https://jobs.lever.co/acme/123-abc"},
            ]))
        )
        rotator = QueryRotator(sites=[LEVER_DOMAIN], terms=["software engineer"])
        results = await search_jobs(API_KEY, rotator)

        assert len(results) == 1
        assert results[0] == LeverListing(
            url="https://jobs.lever.co/acme/",
            company_name="SWE at Acme",
            origin_query="software engineer",
            ats="lever",
            token="acme",
        )

    @respx.mock
    async def test_routes_ashby_results_correctly(self):
        respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(200, json=_brave_response([
                {"title": "Eng at Beta", "url": "https://jobs.ashbyhq.com/beta/xyz"},
            ]))
        )
        rotator = QueryRotator(sites=[ASHBYHQ_DOMAIN], terms=["tech"])
        results = await search_jobs(API_KEY, rotator)

        assert results[0].ats == "ashbyhq"
        assert results[0].token == "beta"

    @respx.mock
    async def test_forwards_config_to_api(self):
        route = respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(200, json=_brave_response([]))
        )
        rotator = QueryRotator(sites=[LEVER_DOMAIN], terms=["tech"])
        cfg = SearchConfig(count=10, offset=2, freshness="pw", country="GB")
        await search_jobs(API_KEY, rotator, config=cfg)

        url = str(route.calls.last.request.url)
        assert "count=10" in url
        assert "offset=2" in url
        assert "freshness=pw" in url
        assert "country=GB" in url

    @respx.mock
    async def test_empty_results(self):
        respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(200, json=_brave_response([]))
        )
        assert await search_jobs(API_KEY, QueryRotator(sites=[LEVER_DOMAIN], terms=["x"])) == []

    @respx.mock
    async def test_api_error_raises(self):
        respx.get(BRAVE_SEARCH_URL).mock(return_value=httpx.Response(401))
        with pytest.raises(httpx.HTTPStatusError):
            await search_jobs(API_KEY, QueryRotator(sites=[LEVER_DOMAIN], terms=["tech"]))


# ── fetch_all_terms ───────────────────────────────────────────────────────────


class TestFetchAllTerms:
    @respx.mock
    async def test_returns_two_level_dict(self):
        respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(200, json=_brave_response([]))
        )
        rotator = QueryRotator(sites=[LEVER_DOMAIN, ASHBYHQ_DOMAIN], terms=["tech"])
        results = await fetch_all_terms(API_KEY, rotator)

        assert set(results.keys()) == {LEVER_DOMAIN, ASHBYHQ_DOMAIN}
        assert "tech" in results[LEVER_DOMAIN]
        assert "tech" in results[ASHBYHQ_DOMAIN]

    @respx.mock
    async def test_queries_all_sites_and_terms(self):
        route = respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(200, json=_brave_response([]))
        )
        rotator = QueryRotator(sites=[LEVER_DOMAIN, ASHBYHQ_DOMAIN], terms=["a", "b"])
        await fetch_all_terms(API_KEY, rotator, results_per_term=20)

        # 2 sites × 2 terms × 1 page = 4 requests
        assert route.call_count == 4
        urls = [str(c.request.url) for c in route.calls]
        assert any(f"site%3A{LEVER_DOMAIN}+a" in u for u in urls)
        assert any(f"site%3A{LEVER_DOMAIN}+b" in u for u in urls)
        assert any(f"site%3A{ASHBYHQ_DOMAIN}+a" in u for u in urls)
        assert any(f"site%3A{ASHBYHQ_DOMAIN}+b" in u for u in urls)

    @respx.mock
    async def test_paginates_within_each_term(self):
        route = respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(200, json=_brave_response([
                {"title": f"Job {i}", "url": f"https://jobs.lever.co/co{i}/{i}"}
                for i in range(20)
            ]))
        )
        rotator = QueryRotator(sites=[LEVER_DOMAIN], terms=["tech"])
        await fetch_all_terms(API_KEY, rotator, results_per_term=100)

        # 1 site × 1 term × 5 pages = 5 requests
        assert route.call_count == 5
        offsets = [str(c.request.url).split("offset=")[1].split("&")[0] for c in route.calls]
        assert offsets == ["0", "1", "2", "3", "4"]

    @respx.mock
    async def test_stops_early_on_incomplete_page(self):
        route = respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(200, json=_brave_response([
                {"title": "Job", "url": "https://jobs.lever.co/only/1"}
            ]))
        )
        rotator = QueryRotator(sites=[LEVER_DOMAIN], terms=["tech"])
        await fetch_all_terms(API_KEY, rotator, results_per_term=100)

        assert route.call_count == 1

    @respx.mock
    async def test_defaults_freshness_to_pw(self):
        route = respx.get(BRAVE_SEARCH_URL).mock(
            return_value=httpx.Response(200, json=_brave_response([]))
        )
        rotator = QueryRotator(sites=[LEVER_DOMAIN], terms=["tech"])
        await fetch_all_terms(API_KEY, rotator)

        assert "freshness=pw" in str(route.calls.last.request.url)

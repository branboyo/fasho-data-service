from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.dedup import compute_dedup_hash, is_duplicate, normalize_title


class TestNormalizeTitle:
    def test_lowercases_and_strips(self):
        assert normalize_title("  Shift Lead  ") == "shift lead"

    def test_removes_special_characters(self):
        assert normalize_title("Shift Lead (FT)") == "shift lead ft"

    def test_collapses_whitespace(self):
        assert normalize_title("shift   lead") == "shift lead"

    def test_handles_empty_string(self):
        assert normalize_title("") == ""


class TestComputeDedupHash:
    def test_same_inputs_produce_same_hash(self):
        h1 = compute_dedup_hash(1, "Shift Lead", "San Francisco, CA")
        h2 = compute_dedup_hash(1, "Shift Lead", "San Francisco, CA")
        assert h1 == h2

    def test_different_titles_produce_different_hashes(self):
        h1 = compute_dedup_hash(1, "Shift Lead", "SF")
        h2 = compute_dedup_hash(1, "Cashier", "SF")
        assert h1 != h2

    def test_normalizes_title_before_hashing(self):
        h1 = compute_dedup_hash(1, "Shift Lead", "SF")
        h2 = compute_dedup_hash(1, "  shift  lead  ", "SF")
        assert h1 == h2

    def test_none_location_handled(self):
        h = compute_dedup_hash(1, "Barista", None)
        assert isinstance(h, str) and len(h) == 64


class TestIsDuplicate:
    async def test_returns_false_when_no_match(self, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await is_duplicate(mock_session, "abc123")
        assert result is False

    async def test_returns_true_when_match_exists(self, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 1
        mock_session.execute.return_value = mock_result

        result = await is_duplicate(mock_session, "abc123")
        assert result is True

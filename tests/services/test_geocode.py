from unittest.mock import MagicMock, patch

from app.services.geocode import GeocodeService


class TestGeocodeService:
    async def test_returns_coords_for_valid_location(self):
        mock_location = MagicMock()
        mock_location.latitude = 37.7749
        mock_location.longitude = -122.4194

        with patch("app.services.geocode.Nominatim") as MockNom:
            MockNom.return_value.geocode.return_value = mock_location
            service = GeocodeService(user_agent="test")
            result = await service.geocode("San Francisco, CA")

        assert result == (37.7749, -122.4194)

    async def test_returns_none_for_unresolvable_location(self):
        with patch("app.services.geocode.Nominatim") as MockNom:
            MockNom.return_value.geocode.return_value = None
            service = GeocodeService(user_agent="test")
            result = await service.geocode("Nowheresville, ZZ")

        assert result is None

    async def test_caches_repeated_lookups(self):
        mock_location = MagicMock()
        mock_location.latitude = 40.7128
        mock_location.longitude = -74.0060

        with patch("app.services.geocode.Nominatim") as MockNom:
            mock_geocoder = MockNom.return_value
            mock_geocoder.geocode.return_value = mock_location
            service = GeocodeService(user_agent="test")

            await service.geocode("New York, NY")
            await service.geocode("New York, NY")
            await service.geocode("  new york, ny  ")

        mock_geocoder.geocode.assert_called_once()

    async def test_skips_empty_string(self):
        with patch("app.services.geocode.Nominatim") as MockNom:
            service = GeocodeService(user_agent="test")
            result = await service.geocode("")

        MockNom.return_value.geocode.assert_not_called()
        assert result is None

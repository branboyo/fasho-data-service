import asyncio

from geopy.geocoders import Nominatim


class GeocodeService:
    def __init__(self, user_agent: str = "fasho-data-service"):
        self._geocoder = Nominatim(user_agent=user_agent)
        self._cache: dict[str, tuple[float, float] | None] = {}

    async def geocode(self, location_text: str) -> tuple[float, float] | None:
        normalized = location_text.strip().lower()
        if not normalized:
            return None

        if normalized in self._cache:
            return self._cache[normalized]

        result = await asyncio.to_thread(self._geocoder.geocode, location_text)
        coords = (result.latitude, result.longitude) if result else None
        self._cache[normalized] = coords
        return coords

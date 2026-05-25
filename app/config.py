from pathlib import Path

from pydantic_settings import BaseSettings

_SETTINGS_FILE = Path(__file__).resolve().parent.parent / "local-settings.yaml"

_KEY_MAP = {
    "BRAVE_SEARCH_API_KEY": "brave_api_key",
    "SUPABASE_API_URL": "supabase_url",
    "SUPABASE_API_KEY": "supabase_key",
}


def _load_settings_file() -> dict:
    if not _SETTINGS_FILE.exists():
        return {}
    values: dict[str, str] = {}
    for line in _SETTINGS_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        field = _KEY_MAP.get(key.strip())
        if field:
            values[field] = value.strip()
    return values


class Settings(BaseSettings):
    brave_api_key: str = ""
    supabase_url: str = ""
    supabase_key: str = ""

    model_config = {"env_prefix": "FASHO_"}

    def __init__(self, **kwargs):
        file_values = _load_settings_file()
        # File provides defaults; explicit kwargs and env vars override
        merged = {**file_values, **kwargs}
        super().__init__(**merged)


settings = Settings()

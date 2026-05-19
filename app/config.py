from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://localhost:5432/fasho"
    redis_url: str = "redis://localhost:6379"
    poll_interval_minutes: int = 10
    geocode_user_agent: str = "fasho-data-service"

    model_config = {"env_prefix": "FASHO_"}


settings = Settings()

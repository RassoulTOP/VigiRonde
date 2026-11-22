from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://vigironde:vigironde@localhost:5433/vigironde"
    test_database_url: str = "postgresql+psycopg://vigironde:vigironde@localhost:5433/vigironde_test"
    jwt_secret: str = "dev-secret-a-changer"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 720
    upload_dir: str = "/data/uploads"
    checkpoint_max_distance_m: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()

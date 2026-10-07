"""
Centralized settings, loaded from environment variables / .env.
See .env.example for the full list.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    voyage_api_key: str = ""
    database_url: str = "postgresql://postgres:postgres@localhost:5432/agentic_rag"
    jwt_secret: str = "change-me"

    # ANTHROPIC_API_KEY -> anthropic_api_key, etc.
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", case_sensitive=False)


settings = Settings()

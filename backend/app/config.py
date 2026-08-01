"""
Centralized settings, loaded from environment variables / .env.
See .env.example for the full list.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    database_url: str = "postgresql://postgres:postgres@localhost:5432/agentic_rag"
    jwt_secret: str = "change-me"

    class Config:
        env_file = ".env"
        env_prefix = ""
        # ANTHROPIC_API_KEY -> anthropic_api_key, etc.
        case_sensitive = False


settings = Settings()

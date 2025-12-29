"""Application configuration using Pydantic Settings."""
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql://veritas:veritas_pass@localhost:5432/veritas_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM Configuration
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_provider: Literal["openai", "anthropic", "azure"] = "openai"
    llm_model: str = "gpt-4-turbo-preview"
    llm_temperature: float = 0.0

    # External APIs
    google_maps_api_key: str = ""
    opencorporates_api_key: str = ""
    lexisnexis_api_key: str = ""

    # Security
    agency_token: str = "dev-token-12345"
    secret_key: str = "your-secret-key-change-in-production"

    # Application
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

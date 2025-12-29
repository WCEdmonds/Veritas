"""Application configuration using Pydantic Settings."""
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql://veritas:veritas_pass@localhost:5432/veritas_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Vector & Graph Databases
    chroma_url: str = "http://localhost:8001"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "veritas_graph_pass"

    # LLM Configuration
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_provider: Literal["openai", "anthropic", "azure"] = "openai"
    llm_model: str = "gpt-4-turbo-preview"
    llm_temperature: float = 0.0

    # External APIs
    google_maps_api_key: str = ""
    opencorporates_api_key: str = ""

    # Layer 2: Corporate (Alternative)
    sec_edgar_enabled: bool = True  # Free US corporate data

    # Layer 3: Identity Verification (LexisNexis is OPTIONAL)
    enable_lexisnexis: bool = False
    lexisnexis_api_key: str = ""
    lexisnexis_endpoint: str = ""

    # Phone Verification Alternatives
    phone_verification_provider: Literal["twilio", "numverify", "pattern", "lexisnexis"] = "pattern"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    numverify_api_key: str = ""

    # Email Verification Alternatives
    email_verification_provider: Literal["hibp", "emailrep", "google", "lexisnexis"] = "hibp"
    hibp_api_key: str = ""  # Have I Been Pwned
    emailrep_api_key: str = ""
    google_search_api_key: str = ""
    google_search_cx: str = ""

    # Breach History Alternatives
    breach_verification_provider: Literal["hibp", "lexisnexis"] = "hibp"

    # Layer 5: Employee Ghost Check
    enable_ghost_check: bool = True
    dmf_source: Literal["direct", "lexisnexis", "disabled"] = "direct"
    dmf_file_path: str = "/data/ssdmf.txt"  # SSA Death Master File

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

"""Project configuration, loaded from environment variables and the `.env` file."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """All runtime settings. Values come from `.env` / environment, with safe defaults."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    llm_provider: str = "gemini"
    gemini_api_key: SecretStr | None = None
    gemini_extraction_model: str = "gemini-3.5-flash-lite"
    gemini_qa_model: str = "gemini-3.8-flash"
    # Used for a call only when the main model stays overloaded after all retries. Empty = no fallback.
    gemini_extraction_fallback_model: str | None = None
    gemini_qa_fallback_model: str | None = None
    gemini_rpm: int = Field(default=10, ge=0, description="Requests per minute per model; 0 = no limit")
    gemini_rpd: int = Field(default=250, ge=0, description="Requests per day per model; 0 = no limit")
    gemini_max_retries: int = Field(default=5, ge=0)

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("")

    # Paths and logging
    data_dir: Path = PROJECT_ROOT / "data"
    log_level: str = "INFO"

    @property
    def api_key(self) -> str | None:
        """The Gemini API key as plain text, or None if it is missing or blank."""
        if self.gemini_api_key is None:
            return None
        value = self.gemini_api_key.get_secret_value().strip()
        return value or None

    def fallback_model(self, purpose: str) -> str | None:
        """The configured fallback for "extraction" or "qa", or None if blank."""
        value = self.gemini_extraction_fallback_model if purpose == "extraction" else self.gemini_qa_fallback_model
        return (value or "").strip() or None

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def llm_cache_dir(self) -> Path:
        return self.cache_dir / "llm"

    @property
    def quota_state_file(self) -> Path:
        """Where the per-day request counter is stored between runs."""
        return self.cache_dir / "daily_quota.json"

    @property
    def companies_csv(self) -> Path:
        return self.data_dir / "companies.csv"

    @property
    def raw_pdf_dir(self) -> Path:
        return self.data_dir / "raw_pdfs"

    @property
    def checksum_file(self) -> Path:
        """sha256 of every downloaded report; committed so downloads can be verified anywhere."""
        return self.data_dir / "pdf_checksums.json"

    @property
    def sections_dir(self) -> Path:
        return self.data_dir / "sections"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the settings singleton (read once per process)."""
    return Settings()


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging once, with a compact format."""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # The HTTP client logs every request at INFO, which drowns out pipeline logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("google_genai").setLevel(logging.WARNING)

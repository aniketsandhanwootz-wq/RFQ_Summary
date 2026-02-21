from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM (Gemini)
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-1.5-pro", alias="GEMINI_MODEL")

    # Perplexity
    perplexity_api_key: str = Field(default="", alias="PERPLEXITY_API_KEY")
    perplexity_base_url: str = Field(default="https://api.perplexity.ai", alias="PERPLEXITY_BASE_URL")
    perplexity_model: str = Field(default="sonar", alias="PERPLEXITY_MODEL")
    perplexity_max_results: int = Field(default=5, alias="PERPLEXITY_MAX_RESULTS")

    # Limits
    max_attachment_bytes: int = Field(default=50 * 1024 * 1024, alias="MAX_ATTACHMENT_BYTES")
    max_pdf_pages: int = Field(default=60, alias="MAX_PDF_PAGES")

    # Output
    output_dir: str = Field(default="./out", alias="OUTPUT_DIR")
    output_mode: str = Field(default="local", alias="OUTPUT_MODE")  # local | (future: db/glide)

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


def load_settings() -> Settings:
    return Settings()
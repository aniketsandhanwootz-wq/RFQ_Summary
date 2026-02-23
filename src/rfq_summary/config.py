from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM (Gemini)
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-1.5-flash", alias="GEMINI_MODEL")
    gemini_model_fallbacks: str = Field(
        default="gemini-1.5-flash,gemini-2.0-flash,gemini-2.0-flash-lite",
        alias="GEMINI_MODEL_FALLBACKS",
    )

    # Prompts (two endpoints)
    prompt_pricing_file: str = Field(default="prompts/pricing_estimate.md", alias="PROMPT_PRICING_FILE")
    prompt_summary_file: str = Field(default="prompts/rfq_summary.md", alias="PROMPT_SUMMARY_FILE")

    # Perplexity
    perplexity_api_key: str = Field(default="", alias="PERPLEXITY_API_KEY")
    perplexity_base_url: str = Field(default="https://api.perplexity.ai", alias="PERPLEXITY_BASE_URL")
    perplexity_model: str = Field(default="sonar", alias="PERPLEXITY_MODEL")
    perplexity_max_results: int = Field(default=6, alias="PERPLEXITY_MAX_RESULTS")

    # Limits
    max_attachment_bytes: int = Field(default=50 * 1024 * 1024, alias="MAX_ATTACHMENT_BYTES")
    max_pdf_pages: int = Field(default=60, alias="MAX_PDF_PAGES")

    min_pdf_text_chars_per_page: int = Field(default=40, alias="MIN_PDF_TEXT_CHARS_PER_PAGE")
    min_ocr_chars_to_accept: int = Field(default=80, alias="MIN_OCR_CHARS_TO_ACCEPT")
    enable_gemini_vision_fallback: bool = Field(default=True, alias="ENABLE_GEMINI_VISION_FALLBACK")

    max_excel_rows: int = Field(default=250, alias="MAX_EXCEL_ROWS")
    max_excel_cols: int = Field(default=40, alias="MAX_EXCEL_COLS")
    max_excel_tables_per_sheet: int = Field(default=5, alias="MAX_EXCEL_TABLES_PER_SHEET")

    # Glide writeback (SAFETY: default off)
    enable_glide_writeback: bool = Field(default=False, alias="ENABLE_GLIDE_WRITEBACK")

    glide_api_key: str = Field(default="", alias="GLIDE_API_KEY")
    glide_app_id: str = Field(default="", alias="GLIDE_APP_ID")
    glide_rfq_table: str = Field(default="", alias="GLIDE_RFQ_TABLE")
    glide_col_rfq_summary: str = Field(default="dWgLs", alias="GLIDE_COL_RFQ_SUMMARY")
    glide_col_price_estimate: str = Field(default="PRfRY", alias="GLIDE_COL_PRICE_ESTIMATE")
    glide_col_price_reasoning: str = Field(default="jblXm", alias="GLIDE_COL_PRICE_REASONING")

    # Google Sheet logging (SAFETY: optional)
    enable_sheets_logging: bool = Field(default=True, alias="ENABLE_SHEETS_LOGGING")
    log_sheet_id: str = Field(default="", alias="LOG_SHEET_ID")
    log_sheet_tab: str = Field(default="Logs", alias="LOG_SHEET_TAB")
    google_sa_json_b64: str = Field(default="", alias="GOOGLE_SA_JSON_B64")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Cell limits (Sheets cell practical limit)
    max_cell_chars: int = Field(default=50000, alias="MAX_CELL_CHARS")


def load_settings() -> Settings:
    return Settings()
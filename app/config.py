"""Application settings, read from environment variables (or a .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Tiny .env loader so we don't need an extra dependency.

    Lines look like KEY=value. Existing environment variables win.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    llm_provider: str  # "anthropic" | "openai" | "offline"
    anthropic_model: str
    openai_model: str
    ocr_min_confidence: float  # below this we try the vision fallback
    ocr_lang: str
    max_upload_mb: int
    max_pdf_pages: int


def get_settings() -> Settings:
    _load_dotenv()
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if not provider:
        # Pick automatically based on which API key is available.
        if os.getenv("ANTHROPIC_API_KEY"):
            provider = "anthropic"
        elif os.getenv("OPENAI_API_KEY"):
            provider = "openai"
        else:
            provider = "offline"

    return Settings(
        llm_provider=provider,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        ocr_min_confidence=float(os.getenv("OCR_MIN_CONFIDENCE", "70")),
        ocr_lang=os.getenv("OCR_LANG", "eng"),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "10")),
        max_pdf_pages=int(os.getenv("MAX_PDF_PAGES", "5")),
    )

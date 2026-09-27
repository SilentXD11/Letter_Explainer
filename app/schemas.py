"""Request / response models (validated by Pydantic, shown in /docs)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Action(BaseModel):
    action: str
    deadline: str | None = None  # ISO date or free text like "within 14 days"


class Deadline(BaseModel):
    date: str
    description: str


class GlossaryItem(BaseModel):
    term: str
    meaning: str


class Explanation(BaseModel):
    summary: str = Field(description="2-4 plain-English sentences: what is this letter and what does it want?")
    sender: str | None = None
    letter_type: str = "general"
    urgency: Literal["low", "medium", "high"] = "low"
    urgency_reason: str = ""
    key_points: list[str] = []
    actions: list[Action] = []
    deadlines: list[Deadline] = []
    amounts: list[str] = []
    reference_numbers: list[str] = []
    glossary: list[GlossaryItem] = []
    scam_warning: str | None = None
    draft_reply: str = ""
    disclaimer: str = (
        "This is an automated explanation, not legal or financial advice. "
        "Check important details against the original letter, and contact the sender "
        "or Citizens Advice if you are unsure."
    )


class Extraction(BaseModel):
    source: Literal["image", "pdf", "text"]
    method: str  # tesseract | vision_llm | pdf_text_layer | pdf_ocr | user_text
    text: str
    confidence: float | None = None
    ocr_variant: str | None = None
    quality: dict | None = None
    warnings: list[str] = []
    needs_retake: bool = False
    retake_tips: list[str] = []


class ExplainResponse(BaseModel):
    extraction: Extraction
    explanation: Explanation | None = None
    provider: str


class ExplainTextRequest(BaseModel):
    text: str = Field(min_length=20, max_length=30000)
    language: str = Field(default="English", max_length=40)

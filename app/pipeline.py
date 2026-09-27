"""The end-to-end flow: file -> text (with quality checks) -> explanation.

How we deal with photos where the text is hard to see (5 layers):
  1. Quality check  - measure blur, darkness, glare, resolution and give
                      specific "retake" tips instead of silently failing.
  2. Pre-processing - find & flatten the page, remove shadows, deskew,
                      enhance contrast, binarise.
  3. Best-of-N OCR  - run Tesseract on several cleaned variants and keep the
                      one with the highest word confidence.
  4. Vision fallback- if OCR confidence is still low, send the cleaned page
                      to a vision LLM (Claude / GPT) to transcribe it.
  5. Human check    - the extracted text is shown to the user, who can fix
                      mistakes and re-run the explanation (/api/explain-text).
"""

from __future__ import annotations

import logging

from app.config import Settings
from app.extractors import extract_facts
from app.image_quality import assess_quality
from app.llm import LLMError, OfflineProvider, Provider
from app.ocr import ocr_document
from app.pdf_reader import read_pdf
from app.preprocess import encode_jpeg, load_image
from app.schemas import ExplainResponse, Explanation, Extraction

log = logging.getLogger(__name__)

MIN_WORDS = 15  # fewer readable words than this = we didn't really read the letter


def extract_from_file(data: bytes, settings: Settings, provider: Provider) -> Extraction:
    if data[:5] == b"%PDF-":
        return _extract_pdf(data, settings)
    return _extract_image(data, settings, provider)


def _extract_pdf(data: bytes, settings: Settings) -> Extraction:
    pdf = read_pdf(data, max_pages=settings.max_pdf_pages, lang=settings.ocr_lang)
    warnings = []
    if pdf.method == "pdf_ocr" and (pdf.confidence or 0) < settings.ocr_min_confidence:
        warnings.append("This PDF is a scan and some text may have been read incorrectly. Please check it.")
    return Extraction(
        source="pdf", method=pdf.method, text=pdf.text, confidence=pdf.confidence,
        warnings=warnings, needs_retake=len(pdf.text.split()) < MIN_WORDS,
        retake_tips=["We could not find much text in this PDF. Try a clearer scan."]
        if len(pdf.text.split()) < MIN_WORDS else [],
    )


def _extract_image(data: bytes, settings: Settings, provider: Provider) -> Extraction:
    img = load_image(data)
    quality = assess_quality(img)
    ocr, clean_page = ocr_document(img, lang=settings.ocr_lang)

    extraction = Extraction(
        source="image",
        method="tesseract",
        text=ocr.text,
        confidence=ocr.confidence,
        ocr_variant=ocr.variant,
        quality=quality.to_dict(),
        warnings=list(quality.tips),
    )

    ocr_is_weak = ocr.confidence < settings.ocr_min_confidence or ocr.word_count < MIN_WORDS
    if not ocr_is_weak:
        return extraction

    # Layer 4: ask a vision model to read the (cleaned-up, colour) page.
    if provider.supports_vision:
        try:
            text = provider.transcribe_image(encode_jpeg(clean_page))
            if len(text.split()) >= MIN_WORDS:
                extraction.text = text
                extraction.method = "vision_llm"
                extraction.warnings.append(
                    "Standard OCR struggled with this photo, so an AI vision model read it instead. "
                    "Please check the text below."
                )
                return extraction
        except LLMError as exc:
            log.warning("Vision fallback failed: %s", exc)
            extraction.warnings.append("AI vision fallback was unavailable.")

    # Still weak: keep what we have but ask for a better photo.
    extraction.needs_retake = True
    extraction.retake_tips = quality.tips or [
        "Lay the letter flat on a dark table, in daylight, without flash.",
        "Hold the phone directly above the page so all four corners are visible.",
        "Tap on the text to focus and hold still for a second.",
    ]
    extraction.warnings.append(
        f"The text could only be read with low confidence ({ocr.confidence:.0f}%). "
        "Check and correct the text below, or take a clearer photo."
    )
    return extraction


def explain_text(text: str, language: str, provider: Provider) -> tuple[Explanation, str]:
    """Explain text. If the LLM fails, fall back to offline rules so the user still gets help."""
    facts = extract_facts(text)
    try:
        return provider.explain(text, facts, language), provider.name
    except LLMError as exc:
        log.warning("LLM failed, using offline rules: %s", exc)
        return OfflineProvider().explain(text, facts, language), "offline (fallback)"


def process_file(data: bytes, language: str, settings: Settings, provider: Provider) -> ExplainResponse:
    extraction = extract_from_file(data, settings, provider)
    if extraction.needs_retake or len(extraction.text.split()) < 5:
        # Don't explain garbled text - a wrong explanation of an official letter is
        # worse than none. The user can retake the photo or correct the text.
        return ExplainResponse(extraction=extraction, explanation=None, provider=provider.name)
    explanation, used = explain_text(extraction.text, language, provider)
    return ExplainResponse(extraction=extraction, explanation=explanation, provider=used)

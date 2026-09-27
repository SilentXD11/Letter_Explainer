"""Run Tesseract OCR on several pre-processed variants and keep the best."""

from __future__ import annotations

import math
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract

from app.preprocess import estimate_skew_angle, make_variants, prepare_document, rotate

# Each Tesseract process should use one thread; we run variants in parallel instead.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

GOOD_ENOUGH_CONFIDENCE = 85.0  # stop trying other variants once we reach this
TESSERACT_CONFIG = "--oem 3 --psm 3"


class OCRUnavailableError(RuntimeError):
    pass


@dataclass
class OCRResult:
    text: str
    confidence: float  # mean word confidence 0-100 (weighted by word length)
    word_count: int  # words read with confidence >= 50
    variant: str
    scores: dict[str, float]


def ensure_tesseract() -> str:
    if shutil.which(pytesseract.pytesseract.tesseract_cmd) is None:
        raise OCRUnavailableError("Tesseract is not installed. See README -> 'Install Tesseract'.")
    return str(pytesseract.get_tesseract_version())


def ocr_single(img: np.ndarray, lang: str = "eng", name: str = "image") -> OCRResult:
    """OCR one image. Uses image_to_data so we get text AND per-word confidence
    from a single Tesseract call."""
    data = pytesseract.image_to_data(img, lang=lang, config=TESSERACT_CONFIG, output_type=pytesseract.Output.DICT)
    total, weight, words = 0.0, 0, 0
    lines: dict[tuple[int, int, int], list[str]] = {}
    for i, raw in enumerate(data["text"]):
        word = (raw or "").strip()
        conf = float(data["conf"][i])
        if not word or conf < 0:
            continue
        total += conf * len(word)
        weight += len(word)
        if conf >= 50 and any(c.isalnum() for c in word):
            words += 1
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)

    # Rebuild text: one line per Tesseract line, blank line between paragraphs.
    out: list[str] = []
    prev_par = None
    for (block, par, _line), ws in lines.items():
        if prev_par is not None and (block, par) != prev_par:
            out.append("")
        out.append(" ".join(ws))
        prev_par = (block, par)

    conf = total / weight if weight else 0.0
    return OCRResult("\n".join(out).strip(), round(conf, 1), words, name, {name: round(conf, 1)})


def _score(r: OCRResult, max_words: int) -> float:
    # Prefer high confidence, but penalise variants that lost many words
    # (aggressive thresholding can make a page "confident" but nearly empty).
    return r.confidence * math.sqrt(r.word_count / max(max_words, 1))


def best_of_variants(variants: dict[str, np.ndarray], lang: str = "eng") -> OCRResult:
    """Try the usually-best variant first; only if it is not good enough,
    OCR the remaining variants in parallel and keep the best."""
    order = ["shadow_removed", "gray", "adaptive_threshold", "otsu"]
    names = [n for n in order if n in variants] + [n for n in variants if n not in order]

    first = ocr_single(variants[names[0]], lang, names[0])
    if first.confidence >= GOOD_ENOUGH_CONFIDENCE and first.word_count >= 15:
        return first

    with ThreadPoolExecutor(max_workers=min(4, len(names) - 1) or 1) as pool:
        rest = list(pool.map(lambda n: ocr_single(variants[n], lang, n), names[1:]))
    results = [first, *rest]
    max_words = max(r.word_count for r in results)
    best = max(results, key=lambda r: _score(r, max_words))
    best.scores = {r.variant: round(_score(r, max_words), 1) for r in results}
    return best


def fix_orientation(img: np.ndarray) -> np.ndarray | None:
    """Use Tesseract's orientation detection for pages that are sideways or
    upside down. Returns the rotated image, or None if no rotation is needed."""
    try:
        osd = pytesseract.image_to_osd(img, config="--psm 0 -c min_characters_to_try=5")
    except pytesseract.TesseractError:
        return None  # not enough text to decide
    rotations = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}
    for line in osd.splitlines():
        if line.startswith("Rotate:"):
            degrees = int(line.split(":")[1].strip())
            if degrees in rotations:
                return cv2.rotate(img, rotations[degrees])
    return None


def ocr_document(img: np.ndarray, lang: str = "eng") -> tuple[OCRResult, np.ndarray]:
    """Full photo -> text. Returns the result and the cleaned colour page
    (the page is what we send to a vision model if OCR is not good enough)."""
    ensure_tesseract()
    doc = prepare_document(img)
    result = best_of_variants(make_variants(doc), lang)

    # Low confidence might mean the page is sideways/upside down: check and retry.
    if result.confidence < 60 or result.word_count < 15:
        rotated = fix_orientation(doc)
        if rotated is not None:
            retry = best_of_variants(make_variants(rotated), lang)
            if retry.confidence > result.confidence:
                return retry, rotated
    return result, doc


def ocr_clean_page(img: np.ndarray, lang: str = "eng") -> OCRResult:
    """OCR for already-clean pages (e.g. a scanned PDF rendered to an image)."""
    ensure_tesseract()
    gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = rotate(gray, estimate_skew_angle(gray))
    return ocr_single(gray, lang, "pdf_page")

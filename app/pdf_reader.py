"""Read text from PDFs. Digital PDFs have a text layer; scanned ones need OCR."""

from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np
import pypdfium2 as pdfium
from pypdf import PdfReader

from app.ocr import ocr_clean_page

MIN_CHARS_PER_PAGE = 40  # below this we assume the page is a scanned image


@dataclass
class PDFText:
    text: str
    method: str  # "pdf_text_layer" | "pdf_ocr"
    pages: int
    confidence: float | None


def read_pdf(data: bytes, max_pages: int = 5, lang: str = "eng") -> PDFText:
    reader = PdfReader(io.BytesIO(data))
    n_pages = min(len(reader.pages), max_pages)
    texts = [(reader.pages[i].extract_text() or "").strip() for i in range(n_pages)]

    if n_pages and sum(len(t) for t in texts) >= MIN_CHARS_PER_PAGE * n_pages:
        return PDFText("\n\n".join(texts).strip(), "pdf_text_layer", n_pages, None)

    # Scanned PDF: render each page at 300 DPI and OCR it.
    pdf = pdfium.PdfDocument(data)
    page_texts, confs = [], []
    for i in range(min(len(pdf), max_pages)):
        pil = pdf[i].render(scale=300 / 72).to_pil().convert("RGB")
        img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        result = ocr_clean_page(img, lang=lang)
        page_texts.append(result.text)
        confs.append(result.confidence)
    pdf.close()
    conf = round(sum(confs) / len(confs), 1) if confs else 0.0
    return PDFText("\n\n".join(page_texts).strip(), "pdf_ocr", len(page_texts), conf)

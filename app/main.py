"""FastAPI app. Run with:  uvicorn app.main:app --reload"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.llm import get_provider
from app.ocr import OCRUnavailableError, ensure_tesseract
from app.pipeline import explain_text, extract_from_file, process_file
from app.preprocess import UnreadableImageError
from app.schemas import ExplainResponse, ExplainTextRequest, Extraction

logging.basicConfig(level=logging.INFO)
STATIC = Path(__file__).parent / "static"
ALLOWED_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "image/tiff",
    "image/bmp", "application/pdf", "application/octet-stream",
}

app = FastAPI(
    title="Letter Explainer",
    description="Upload a photo or PDF of a confusing letter and get a plain-English explanation.",
    version="1.0.0",
)
app.state.settings = get_settings()
app.state.provider = get_provider(app.state.settings)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


async def _read_upload(request: Request, file: UploadFile) -> bytes:
    settings = request.app.state.settings
    if file.content_type and file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, f"Unsupported file type: {file.content_type}. Use a photo (JPG/PNG) or PDF.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "The file is empty.")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB.")
    return data


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/sw.js", include_in_schema=False)
def service_worker() -> FileResponse:
    # Served from the root so it can control the whole site (installable app).
    return FileResponse(STATIC / "sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest() -> FileResponse:
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/health")
def health(request: Request) -> dict:
    try:
        tesseract = ensure_tesseract()
    except OCRUnavailableError:
        tesseract = None
    provider = request.app.state.provider
    return {
        "status": "ok",
        "provider": provider.name,
        "vision_fallback": provider.supports_vision,
        "tesseract": tesseract,
    }


@app.post("/api/extract", response_model=Extraction)
async def extract(request: Request, file: UploadFile = File(...)) -> Extraction:
    """Only read the text (with quality checks). Useful to review before explaining."""
    data = await _read_upload(request, file)
    try:
        return extract_from_file(data, request.app.state.settings, request.app.state.provider)
    except UnreadableImageError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OCRUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/explain", response_model=ExplainResponse)
async def explain(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form("English"),
) -> ExplainResponse:
    """Read the letter and explain it."""
    data = await _read_upload(request, file)
    try:
        return process_file(data, language[:40], request.app.state.settings, request.app.state.provider)
    except UnreadableImageError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OCRUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/explain-text", response_model=ExplainResponse)
def explain_plain_text(request: Request, body: ExplainTextRequest) -> ExplainResponse:
    """Explain text the user typed, pasted, or corrected after OCR."""
    explanation, used = explain_text(body.text, body.language, request.app.state.provider)
    return ExplainResponse(
        extraction=Extraction(source="text", method="user_text", text=body.text),
        explanation=explanation,
        provider=used,
    )

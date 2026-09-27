import io

from fastapi.testclient import TestClient
from PIL import Image

from app.llm import OfflineProvider
from app.main import app
from tests.conftest import make_text_pdf, to_jpeg

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["provider"] == "offline"
    assert body["tesseract"]


def test_homepage_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "Letter Explainer" in r.text


def test_explain_photo(hard_photo):
    r = client.post("/api/explain", files={"file": ("letter.jpg", to_jpeg(hard_photo), "image/jpeg")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["extraction"]["method"] == "tesseract"
    assert body["extraction"]["needs_retake"] is False
    assert "£142.50" in body["explanation"]["amounts"]
    assert body["explanation"]["urgency"] == "high"


def test_unreadable_photo_asks_for_retake(unreadable_photo):
    r = client.post("/api/explain", files={"file": ("bad.jpg", to_jpeg(unreadable_photo), "image/jpeg")})
    assert r.status_code == 200
    ext = r.json()["extraction"]
    assert ext["needs_retake"] is True
    assert ext["retake_tips"]
    assert r.json()["explanation"] is None  # never explain garbled text


def test_explain_text_pdf(letter_text):
    pdf = make_text_pdf(letter_text.replace("£", "GBP "))
    r = client.post("/api/explain", files={"file": ("letter.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["extraction"]["method"] == "pdf_text_layer"
    assert "CT-4829-1173" in body["explanation"]["reference_numbers"]


def test_explain_scanned_pdf(clean_page):
    img = Image.fromarray(clean_page[:, :, ::-1])
    buf = io.BytesIO()
    img.save(buf, format="PDF", resolution=200)
    r = client.post("/api/explain", files={"file": ("scan.pdf", buf.getvalue(), "application/pdf")})
    assert r.status_code == 200, r.text
    assert r.json()["extraction"]["method"] == "pdf_ocr"
    assert "CT-4829-1173" in r.json()["extraction"]["text"]


def test_explain_corrected_text(letter_text):
    r = client.post("/api/explain-text", json={"text": letter_text, "language": "English"})
    assert r.status_code == 200
    assert r.json()["explanation"]["sender"] == "Riverside Borough Council"


def test_rejects_non_image():
    r = client.post("/api/explain", files={"file": ("x.jpg", b"not an image at all", "image/jpeg")})
    assert r.status_code == 422


def test_rejects_wrong_type():
    r = client.post("/api/explain", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 415


class FakeVisionProvider(OfflineProvider):
    """Pretends to be Claude/GPT reading the image, so we can test the fallback path."""

    name = "fake-vision"
    supports_vision = True

    def transcribe_image(self, jpeg: bytes) -> str:
        from samples.make_sample_letter import LETTER_TEXT

        return LETTER_TEXT


def test_vision_fallback_used_when_ocr_fails(unreadable_photo):
    original = app.state.provider
    app.state.provider = FakeVisionProvider()
    try:
        r = client.post("/api/explain", files={"file": ("bad.jpg", to_jpeg(unreadable_photo), "image/jpeg")})
    finally:
        app.state.provider = original
    ext = r.json()["extraction"]
    assert ext["method"] == "vision_llm"
    assert ext["needs_retake"] is False
    assert "CT-4829-1173" in ext["text"]

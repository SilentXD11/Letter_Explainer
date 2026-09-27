import os

import cv2
import numpy as np
import pytest

os.environ["LLM_PROVIDER"] = "offline"  # tests never call a paid API

from samples.make_sample_letter import LETTER_TEXT, render_letter, simulate_photo  # noqa: E402

KEY_FACTS = ["5 October 2026", "£142.50", "CT-4829-1173", "liability order"]


def to_jpeg(img: np.ndarray, quality: int = 85) -> bytes:
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])[1].tobytes()


def make_text_pdf(text: str) -> bytes:
    """Build a tiny valid PDF with a real text layer (no extra libraries)."""
    lines = [ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for ln in text.splitlines()]
    ops = ["BT", "/F1 11 Tf", "14 TL", "50 800 Td"] + [f"({ln}) '" for ln in lines] + ["ET"]
    stream = "\n".join(ops).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(out)


@pytest.fixture(scope="session")
def clean_page() -> np.ndarray:
    return render_letter()


@pytest.fixture(scope="session")
def normal_photo(clean_page) -> np.ndarray:
    return simulate_photo(clean_page)


@pytest.fixture(scope="session")
def hard_photo(clean_page) -> np.ndarray:
    """Tilted, strong shadow, a little blur, darker: plain Tesseract fails on this."""
    return simulate_photo(clean_page, angle=11, shadow=0.8, blur=2, darkness=0.8, noise=12, seed=3)


@pytest.fixture(scope="session")
def unreadable_photo(clean_page) -> np.ndarray:
    """So blurry and dark that no software can recover it -> should ask for a retake."""
    return simulate_photo(clean_page, angle=-9, shadow=0.7, blur=13, darkness=0.5, noise=14, seed=1)


@pytest.fixture(scope="session")
def letter_text() -> str:
    return LETTER_TEXT

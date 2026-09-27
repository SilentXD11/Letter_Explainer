import cv2
import pytest

from app.config import get_settings
from app.ocr import ocr_document, ocr_single
from app.preprocess import estimate_skew_angle, remove_shadows, rotate
from tests.conftest import KEY_FACTS


def found(text: str) -> int:
    return sum(fact in text for fact in KEY_FACTS)


@pytest.mark.parametrize("angle", [-7, 5])
def test_deskew_recovers_angle(clean_page, angle):
    gray = cv2.cvtColor(clean_page, cv2.COLOR_BGR2GRAY)
    tilted = rotate(gray, angle)
    estimated = estimate_skew_angle(tilted)
    assert abs(estimated + angle) <= 1.0  # we must rotate back by -angle


def test_remove_shadows_evens_out_background(hard_photo):
    gray = cv2.cvtColor(hard_photo, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    bright = gray[h // 4: h // 3, w // 4: w // 3]
    dark = gray[2 * h // 3: 3 * h // 4, 2 * w // 3: 3 * w // 4]
    clean = remove_shadows(gray)
    before = abs(float(bright.mean()) - float(dark.mean()))
    after = abs(float(clean[h // 4: h // 3, w // 4: w // 3].mean())
                - float(clean[2 * h // 3: 3 * h // 4, 2 * w // 3: 3 * w // 4].mean()))
    assert after < before


def test_clean_page_is_read_perfectly(clean_page):
    result, _ = ocr_document(clean_page)
    assert result.confidence > 85
    assert found(result.text) == len(KEY_FACTS)


def test_preprocessing_rescues_hard_photo(hard_photo):
    """The key test: plain Tesseract fails, our pipeline reads it."""
    raw = ocr_single(hard_photo)
    result, _ = ocr_document(hard_photo)
    assert result.confidence > raw.confidence + 30
    assert found(result.text) >= 3
    assert found(result.text) > found(raw.text)


def test_sideways_photo_is_rotated(normal_photo):
    sideways = cv2.rotate(normal_photo, cv2.ROTATE_90_COUNTERCLOCKWISE)
    result, _ = ocr_document(sideways)
    assert result.confidence > 80
    assert found(result.text) >= 3


def test_unreadable_photo_has_low_confidence(unreadable_photo):
    """Below the threshold the app asks for a retake or uses the vision model."""
    result, _ = ocr_document(unreadable_photo)
    assert result.confidence < get_settings().ocr_min_confidence

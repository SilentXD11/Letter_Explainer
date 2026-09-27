import cv2

from app.image_quality import assess_quality


def test_clean_page_passes(clean_page):
    report = assess_quality(clean_page)
    assert report.ok, report.issues


def test_normal_photo_passes(normal_photo):
    assert assess_quality(normal_photo).ok


def test_blurry_and_dark_photo_is_flagged(unreadable_photo):
    report = assess_quality(unreadable_photo)
    assert "blurry" in report.issues
    assert "too_dark" in report.issues
    assert report.tips, "user should get concrete advice on how to retake the photo"


def test_tiny_image_is_flagged(clean_page):
    tiny = cv2.resize(clean_page, (300, 424))
    assert "low_resolution" in assess_quality(tiny).issues

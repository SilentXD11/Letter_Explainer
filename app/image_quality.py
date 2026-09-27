"""Check whether a photo is good enough to read *before* we try OCR.

This is the first line of defence against "the text is not visible":
instead of silently returning garbage, we measure the photo and tell
the user exactly what is wrong (blurry, too dark, glare, too small)
and how to fix it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

# Thresholds are heuristics tuned on phone photos of A4 letters.
MIN_SHORT_SIDE_PX = 600  # smaller than this and small print becomes unreadable
BLUR_THRESHOLD = 60.0  # variance of Laplacian (measured at a fixed width)
DARK_THRESHOLD = 70  # mean brightness 0-255
BRIGHT_THRESHOLD = 235
LOW_CONTRAST_THRESHOLD = 25  # std-dev of brightness
GLARE_RATIO_THRESHOLD = 0.04  # share of fully clipped (white) pixels


@dataclass
class QualityReport:
    width: int
    height: int
    blur_score: float
    brightness: float
    contrast: float
    glare_ratio: float
    issues: list[str] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "blur_score": round(self.blur_score, 1),
            "brightness": round(self.brightness, 1),
            "contrast": round(self.contrast, 1),
            "glare_ratio": round(self.glare_ratio, 4),
            "ok": self.ok,
            "issues": self.issues,
            "tips": self.tips,
        }


def _to_gray(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def blur_score(gray: np.ndarray) -> float:
    """Variance of the Laplacian: sharp edges -> high value, blur -> low value.

    We resize to a fixed width first so the score does not depend on the
    camera's resolution.
    """
    h, w = gray.shape[:2]
    target_w = 1000
    if w != target_w:
        gray = cv2.resize(gray, (target_w, max(1, int(h * target_w / w))), interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def assess_quality(img: np.ndarray) -> QualityReport:
    gray = _to_gray(img)
    h, w = gray.shape[:2]
    report = QualityReport(
        width=w,
        height=h,
        blur_score=blur_score(gray),
        brightness=float(gray.mean()),
        contrast=float(gray.std()),
        glare_ratio=float((gray >= 254).mean()),
    )

    if min(h, w) < MIN_SHORT_SIDE_PX:
        report.issues.append("low_resolution")
        report.tips.append(
            "The image is very small. Take the photo with your phone's main camera "
            "(not a screenshot or a thumbnail) and fill the frame with the letter."
        )
    if report.blur_score < BLUR_THRESHOLD:
        report.issues.append("blurry")
        report.tips.append(
            "The photo looks blurry. Hold the phone steady (rest your elbows on the "
            "table), tap the screen to focus on the text, and wait a second before shooting."
        )
    if report.brightness < DARK_THRESHOLD:
        report.issues.append("too_dark")
        report.tips.append("The photo is too dark. Move near a window or turn on a light.")
    elif report.brightness > BRIGHT_THRESHOLD and report.contrast < LOW_CONTRAST_THRESHOLD:
        report.issues.append("overexposed")
        report.tips.append("The photo is washed out. Avoid direct sunlight or the flash.")
    elif report.contrast < LOW_CONTRAST_THRESHOLD:
        report.issues.append("low_contrast")
        report.tips.append("The text is faint. Put the letter on a dark, plain surface in even light.")

    # Glare only matters on photos: a clean scan is legitimately mostly white,
    # so we only flag clipped pixels when the page overall is not white.
    if report.glare_ratio > GLARE_RATIO_THRESHOLD and float(np.median(gray)) < 200:
        report.issues.append("glare")
        report.tips.append(
            "There is glare or a bright reflection on the page. Turn off the flash and "
            "tilt the phone slightly so the light doesn't bounce off the paper."
        )
    return report

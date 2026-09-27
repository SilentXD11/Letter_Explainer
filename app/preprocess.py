"""Clean up a phone photo so OCR can read it.

Pipeline:
  1. load + fix phone rotation (EXIF)
  2. find the sheet of paper and flatten it (perspective correction)
  3. resize so letters are big enough for Tesseract (~30px tall capitals)
  4. convert to grayscale and remove shadows / uneven lighting
  5. straighten slightly tilted text (deskew)
  6. produce several variants (gray, contrast-enhanced, binarised) -
     OCR is run on each and the best-scoring one wins.
"""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image, ImageOps


class UnreadableImageError(ValueError):
    """Raised when the uploaded bytes are not an image we can decode."""


def load_image(data: bytes) -> np.ndarray:
    """Decode bytes into an OpenCV BGR image, honouring EXIF orientation.

    Phones often save photos sideways and store the rotation in EXIF
    metadata; OpenCV ignores that, so we let Pillow apply it first.
    """
    try:
        pil = Image.open(io.BytesIO(data))
        pil = ImageOps.exif_transpose(pil)
        pil = pil.convert("RGB")
    except Exception as exc:  # noqa: BLE001 - any decode failure means "not an image"
        raise UnreadableImageError("Could not read this file as an image.") from exc
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def resize_for_ocr(img: np.ndarray, target_width: int = 2000) -> np.ndarray:
    """Upscale small images / downscale huge ones to a width Tesseract likes."""
    h, w = img.shape[:2]
    if 1600 <= w <= 3500:
        return img
    scale = target_width / w
    interp = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=interp)


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """Return corners as top-left, top-right, bottom-right, bottom-left."""
    pts = pts.reshape(4, 2).astype("float32")
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype="float32",
    )


def find_and_flatten_document(img: np.ndarray, min_area_ratio: float = 0.25) -> np.ndarray | None:
    """Detect the paper's four corners and warp it to a flat, top-down view.

    Returns None if no clear page outline is found (e.g. the photo is already
    tightly cropped, or it is a scan) - in that case we use the whole image.
    """
    h, w = img.shape[:2]
    scale = 800 / max(h, w)
    small = cv2.resize(img, (int(w * scale), int(h * scale))) if scale < 1 else img.copy()
    scale = min(scale, 1.0)

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    small_area = small.shape[0] * small.shape[1]
    for cnt in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        if cv2.contourArea(cnt) < min_area_ratio * small_area:
            break
        approx = cv2.approxPolyDP(cnt, 0.02 * cv2.arcLength(cnt, True), True)
        if len(approx) != 4:
            continue
        corners = _order_corners(approx) / scale
        tl, tr, br, bl = corners
        out_w = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
        out_h = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
        # A page that covers ~the whole frame is not worth warping.
        if out_w * out_h > 0.95 * w * h:
            return None
        dst = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], dtype="float32")
        matrix = cv2.getPerspectiveTransform(corners, dst)
        return cv2.warpPerspective(img, matrix, (out_w, out_h))
    return None


def remove_shadows(gray: np.ndarray) -> np.ndarray:
    """Even out lighting: estimate the paper background and divide it out.

    A big median blur of a dilated image erases the text and leaves only the
    background (including shadows and gradients). Dividing by it makes the
    paper uniformly white while keeping the ink dark.
    """
    background = cv2.dilate(gray, np.ones((7, 7), np.uint8))
    background = cv2.medianBlur(background, 31)
    normalized = cv2.divide(gray, background, scale=255)
    return cv2.normalize(normalized, None, 0, 255, cv2.NORM_MINMAX)


def estimate_skew_angle(gray: np.ndarray, max_angle: float = 15.0, step: float = 0.5) -> float:
    """Find the rotation that makes text lines most horizontal.

    Projection-profile method: when text lines are horizontal, the row sums
    of ink alternate sharply between "line" and "gap", so their variance is
    highest. We try angles in [-max_angle, max_angle] and keep the best.
    Returns the angle (degrees) to rotate by to straighten the image.
    """
    h, w = gray.shape[:2]
    scale = 800 / w
    small = cv2.resize(gray, (800, max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    ink = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    center = (ink.shape[1] / 2, ink.shape[0] / 2)

    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_angle, max_angle + step, step):
        m = cv2.getRotationMatrix2D(center, float(angle), 1.0)
        rotated = cv2.warpAffine(ink, m, (ink.shape[1], ink.shape[0]), flags=cv2.INTER_NEAREST)
        score = float(np.var(rotated.sum(axis=1)))
        if score > best_score:
            best_angle, best_score = float(angle), score
    # An answer at the edge of the search range usually means "no clear text lines".
    if abs(best_angle) >= max_angle:
        return 0.0
    return best_angle


def rotate(img: np.ndarray, angle: float) -> np.ndarray:
    """Rotate around the centre, filling the corners with white paper."""
    if abs(angle) < 0.1:
        return img
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    border = 255 if img.ndim == 2 else (255, 255, 255)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=border)


def prepare_document(img: np.ndarray) -> np.ndarray:
    """Steps 2-3: crop/flatten the page and bring it to OCR-friendly size (colour)."""
    flat = find_and_flatten_document(img)
    return resize_for_ocr(flat if flat is not None else img)


def make_variants(color_doc: np.ndarray) -> dict[str, np.ndarray]:
    """Steps 4-6: build several cleaned grayscale/binary versions of the page."""
    gray = cv2.cvtColor(color_doc, cv2.COLOR_BGR2GRAY)
    # Estimate tilt on the shadow-free image: shadows otherwise look like "ink".
    angle = estimate_skew_angle(remove_shadows(gray))
    gray = rotate(gray, angle)

    clean = remove_shadows(gray)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(clean)
    denoised = cv2.medianBlur(clahe, 3)  # removes speckle noise, keeps letter edges
    adaptive = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )
    otsu = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    return {
        "gray": gray,
        "shadow_removed": clahe,
        "adaptive_threshold": adaptive,
        "otsu": otsu,
    }


def encode_jpeg(img: np.ndarray, max_side: int = 2000, quality: int = 90) -> bytes:
    """Compress an image for sending to a vision model."""
    h, w = img.shape[:2]
    if max(h, w) > max_side:
        s = max_side / max(h, w)
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("Could not encode image")
    return buf.tobytes()

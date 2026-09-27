"""Generate realistic test letters: a clean "scan" and a messy "phone photo".

Run:  python -m samples.make_sample_letter
Creates samples/letter_clean.png, samples/letter_photo.jpg, samples/letter_bad_photo.jpg
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

LETTER_TEXT = """Riverside Borough Council
Council Tax Department, 10 High Street, London E1 7AA

Date: 14 September 2026
Account number: CT-4829-1173

Dear Mr Vangari,

FINAL REMINDER: Council Tax arrears

Our records show that you have not paid the instalment of £142.50 that was due on
1 September 2026. The total amount now outstanding for this year is £1,282.50.

You must pay the missed instalment of £142.50 by 5 October 2026. If you do not pay
within 7 days of this notice, you will lose the right to pay by instalments and the
full balance will become due. We may then apply to the magistrates court for a
liability order, which could add costs of £90.00.

How to pay: online at www.riverside.gov.uk/pay, or by phone on 020 7946 0000.
Please quote your account number. If you are having difficulty paying, please
contact us as soon as possible to discuss a payment arrangement or a discount.

Yours sincerely,
Revenue and Benefits Team"""


def _font(size: int) -> ImageFont.ImageFont:
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)  # Pillow >= 10.1


def render_letter(text: str = LETTER_TEXT, width: int = 1654, font_size: int = 30) -> np.ndarray:
    """Render text onto a white A4-ish page (BGR). 1654px wide = A4 at ~200 DPI."""
    height = int(width * 1.414)
    page = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(page)
    font = _font(font_size)
    y = 120
    for line in text.splitlines():
        draw.text((110, y), line, fill=(20, 20, 20), font=font)
        y += int(font_size * 1.6)
    return cv2.cvtColor(np.array(page), cv2.COLOR_RGB2BGR)


def simulate_photo(
    page: np.ndarray,
    angle: float = 6.0,
    shadow: float = 0.55,
    blur: int = 0,
    darkness: float = 1.0,
    noise: float = 8.0,
    seed: int = 0,
) -> np.ndarray:
    """Make a clean page look like a phone photo: on a dark table, tilted,
    in perspective, with a shadow gradient, sensor noise and optional blur."""
    rng = np.random.default_rng(seed)
    h, w = page.shape[:2]
    canvas_w, canvas_h = int(w * 1.35), int(h * 1.3)
    canvas = np.full((canvas_h, canvas_w, 3), (45, 40, 38), np.uint8)  # dark wooden table

    # Perspective: page corners slightly off-rectangle.
    ox, oy = (canvas_w - w) // 2, (canvas_h - h) // 2
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    jitter = w * 0.04
    dst = np.float32([
        [ox + jitter, oy], [ox + w - jitter * 0.5, oy + jitter * 0.6],
        [ox + w, oy + h], [ox - jitter * 0.3, oy + h - jitter * 0.4],
    ])
    m = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(page, m, (canvas_w, canvas_h), borderValue=(0, 0, 0))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), m, (canvas_w, canvas_h))
    canvas[mask > 0] = warped[mask > 0]

    # Rotate the whole shot a little (hand not straight).
    rm = cv2.getRotationMatrix2D((canvas_w / 2, canvas_h / 2), angle, 1.0)
    photo = cv2.warpAffine(canvas, rm, (canvas_w, canvas_h), borderValue=(45, 40, 38)).astype(np.float32)

    # Shadow: brightness falls off towards one corner (like a hand/phone shadow).
    yy, xx = np.mgrid[0:canvas_h, 0:canvas_w].astype(np.float32)
    grad = 1.0 - shadow * ((xx / canvas_w) * 0.6 + (yy / canvas_h) * 0.4)
    photo *= grad[..., None] * darkness
    photo += rng.normal(0, noise, photo.shape)
    photo = np.clip(photo, 0, 255).astype(np.uint8)
    if blur:
        k = blur * 2 + 1
        photo = cv2.GaussianBlur(photo, (k, k), 0)
    return photo


def main() -> None:
    out = Path(__file__).parent
    page = render_letter()
    cv2.imwrite(str(out / "letter_clean.png"), page)
    hard = simulate_photo(page, angle=11, shadow=0.8, blur=2, darkness=0.8, noise=12, seed=3)
    cv2.imwrite(str(out / "letter_photo.jpg"), hard, [cv2.IMWRITE_JPEG_QUALITY, 85])
    bad = simulate_photo(page, angle=-9, shadow=0.7, blur=13, darkness=0.5, noise=14, seed=1)
    cv2.imwrite(str(out / "letter_bad_photo.jpg"), bad, [cv2.IMWRITE_JPEG_QUALITY, 70])
    print(f"Wrote sample letters to {out}")


if __name__ == "__main__":
    main()

"""OCR with different image preparation steps, to find out which one reads scans best.

See SPECS for the variants: resolution (dpi) and steps such as straightening (deskew), median
filter (removes speckle noise), contrast stretch, sharpening and black/white conversion.
Only PIL, numpy, PyMuPDF and Tesseract are used.
"""
import numpy as np
import pymupdf
import pytesseract
from PIL import Image, ImageFilter, ImageOps

# name -> (dpi, steps). Steps are applied in order.
SPECS = {
    "base": (200, ()),
    "dpi150": (150, ()),
    "dpi100": (100, ()),
    "denoise": (200, ("median", "contrast")),
    "deskew": (200, ("deskew",)),
    "denoise_deskew": (200, ("deskew", "median", "contrast")),
    # tried first on a pilot of 12 scans: higher resolution and sharpening made poor scans worse,
    # black/white conversion was 50x slower and much worse
    "dpi300": (300, ()),
    "clean": (300, ("deskew", "contrast", "sharpen")),
    "binary": (300, ("deskew", "contrast", "sharpen", "binarize")),
}
VARIANTS = ("base", "dpi150", "dpi100", "denoise", "deskew", "denoise_deskew")


def render(page: "pymupdf.Page", dpi: int) -> Image.Image:
    pix = page.get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")


def estimate_skew(img: Image.Image, limit: float = 4.0, step: float = 0.25) -> float:
    """Angle (degrees) that makes the text lines most horizontal: maximise the sharpness
    of the row profile of a small, dark-pixel version of the page."""
    small = img.copy()
    small.thumbnail((700, 700))
    arr = np.asarray(small, dtype=np.float32)
    ink = (arr < arr.mean() - 25).astype(np.float32)
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-limit, limit + step, step):
        rotated = Image.fromarray((ink * 255).astype(np.uint8)).rotate(float(angle), resample=Image.BILINEAR, fillcolor=0)
        profile = np.asarray(rotated, dtype=np.float32).sum(axis=1)
        score = float(np.square(np.diff(profile)).sum())
        if score > best_score:
            best_angle, best_score = float(angle), score
    return best_angle


def deskew(img: Image.Image) -> Image.Image:
    return img.rotate(estimate_skew(img), resample=Image.BICUBIC, expand=True, fillcolor=255)


def clean(img: Image.Image) -> Image.Image:
    img = deskew(img)
    img = ImageOps.autocontrast(img, cutoff=1)
    return img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))


def binarize(img: Image.Image, window: int = 41, offset: int = 12) -> Image.Image:
    """Local threshold: a pixel is black when it is clearly darker than its neighbourhood."""
    local_mean = np.asarray(img.filter(ImageFilter.BoxBlur(window // 2)), dtype=np.float32)
    arr = np.asarray(img, dtype=np.float32)
    return Image.fromarray(np.where(arr < local_mean - offset, 0, 255).astype(np.uint8))


def _text(img: Image.Image, lang: str) -> list[str]:
    raw = pytesseract.image_to_string(img, lang=lang, config="--psm 6")
    lines = [" ".join(line.split()).strip(" |") for line in raw.splitlines()]
    return [line for line in lines if line]


def apply_step(img: Image.Image, step: str) -> Image.Image:
    if step == "deskew":
        return deskew(img)
    if step == "median":
        return img.filter(ImageFilter.MedianFilter(3))
    if step == "contrast":
        return ImageOps.autocontrast(img, cutoff=1)
    if step == "sharpen":
        return img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    if step == "binarize":
        return binarize(img)
    raise ValueError(step)


def ocr_lines(pdf_path, variant: str, lang: str = "deu+eng") -> list[str]:
    if variant not in SPECS:
        raise ValueError(f"unknown variant {variant!r}; choose from {tuple(SPECS)}")
    dpi, steps = SPECS[variant]
    doc = pymupdf.open(pdf_path)
    lines: list[str] = []
    for page in doc:
        img = render(page, dpi)
        for step in steps:
            img = apply_step(img, step)
        lines += _text(img, lang)
    doc.close()
    return lines

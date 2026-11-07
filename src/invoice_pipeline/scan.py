"""Turn a digital PDF into a realistic 'scanned' PDF (image only, no text layer).

Three quality profiles. Each scan gets its own seeded generator, so results are
reproducible. Steps: rasterise -> grey -> rotate -> blur -> brightness/contrast
-> noise -> write back as an image-only PDF.
"""
import io
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageFilter


@dataclass(frozen=True)
class ScanProfile:
    name: str
    dpi: int
    max_rotation: float  # degrees, +/-
    blur_radius: float
    noise_sigma: float  # grey levels
    contrast: float  # 1.0 = unchanged
    brightness: float  # grey-level offset


PROFILES = {
    "good": ScanProfile("good", 200, 0.5, 0.4, 4.0, 1.00, 0),
    "typical": ScanProfile("typical", 150, 1.5, 0.8, 8.0, 0.90, -8),
    "poor": ScanProfile("poor", 120, 2.5, 1.0, 12.0, 0.80, -15),
}
PROFILE_ORDER = ("good", "typical", "poor")


def degrade_page(img: Image.Image, profile: ScanProfile, rng: random.Random) -> Image.Image:
    img = img.convert("L")
    angle = rng.uniform(-profile.max_rotation, profile.max_rotation)
    img = img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=255)
    if profile.blur_radius > 0:
        img = img.filter(ImageFilter.GaussianBlur(profile.blur_radius))
    arr = np.asarray(img, dtype=np.float32)
    arr = (arr - 128.0) * profile.contrast + 128.0 + profile.brightness
    np_rng = np.random.default_rng(rng.randrange(2**32))
    arr = arr + np_rng.normal(0.0, profile.noise_sigma, arr.shape)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="L")


def make_scan(src: Path, dst: Path, profile: ScanProfile, seed: int) -> None:
    rng = random.Random(seed)
    src_doc = pymupdf.open(src)
    out = pymupdf.open()
    for page in src_doc:
        pix = page.get_pixmap(dpi=profile.dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img = degrade_page(img, profile, rng)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        # keep the physical page size of the original (points)
        new_page = out.new_page(width=page.rect.width, height=page.rect.height)
        new_page.insert_image(new_page.rect, stream=buf.getvalue())
    src_doc.close()
    out.save(dst, deflate=True)
    out.close()


def assign_profiles(combos: list[tuple[str, str]]) -> list[str]:
    """Spread the 3 profiles evenly overall and inside every (layout, locale) cell."""
    seen: dict[tuple[str, str], int] = {}
    cell_index = {c: i for i, c in enumerate(sorted(set(combos)))}
    result = []
    for combo in combos:
        k = seen.get(combo, 0)
        seen[combo] = k + 1
        result.append(PROFILE_ORDER[(k + cell_index[combo]) % 3])
    return result
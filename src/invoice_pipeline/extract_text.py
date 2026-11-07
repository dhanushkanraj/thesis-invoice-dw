"""Get the text of an invoice PDF as a list of visual lines.

Digital PDFs: read the words with their positions (PyMuPDF) and group words
that share a baseline into one line, so a label and its value end up on one
line even when the PDF stores them far apart.
Scanned PDFs (no text layer): render the page and run Tesseract OCR.
"""
import os

import pymupdf
import pytesseract
from PIL import Image

LINE_TOLERANCE = 2.5  # points: words whose bottom edges differ less than this share a line
MIN_NATIVE_CHARS = 30  # fewer characters than this = treat the page as a scan


def configure_tesseract() -> None:
    path = os.getenv("TESSERACT_PATH")
    if path:
        pytesseract.pytesseract.tesseract_cmd = path


def native_lines(page: "pymupdf.Page") -> list[str]:
    words = page.get_text("words")  # x0, y0, x1, y1, text, block, line, word
    # group by the bottom edge: words of different font sizes on one row share it
    words.sort(key=lambda w: (w[3], w[0]))
    lines: list[list] = []
    bottoms: list[float] = []
    for w in words:
        if lines and abs(w[3] - bottoms[-1]) <= LINE_TOLERANCE:
            lines[-1].append(w)
        else:
            lines.append([w])
            bottoms.append(w[3])
    return [" ".join(w[4] for w in sorted(line, key=lambda w: w[0])) for line in lines]


def ocr_lines(page: "pymupdf.Page", lang: str, dpi: int = 200) -> list[str]:
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    text = pytesseract.image_to_string(img, lang=lang, config="--psm 6")
    lines = [" ".join(line.split()).strip(" |") for line in text.splitlines()]  # table borders show up as '|'
    return [line for line in lines if line]


def get_lines(pdf_path, ocr_lang: str = "deu+eng") -> tuple[list[str], str]:
    """Return (lines, method) where method is 'native' or 'ocr'."""
    doc = pymupdf.open(pdf_path)
    lines: list[str] = []
    methods = set()
    for page in doc:
        if len(page.get_text().strip()) >= MIN_NATIVE_CHARS:
            lines += native_lines(page)
            methods.add("native")
        else:
            lines += ocr_lines(page, ocr_lang)
            methods.add("ocr")
    doc.close()
    return lines, "+".join(sorted(methods))

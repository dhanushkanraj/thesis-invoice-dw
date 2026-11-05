"""Phase 1 environment verification. Run from the project root."""
import io
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def check(name, func):
    try:
        print(f"[ OK ] {name}: {func()}")
        return True
    except Exception as e:
        print(f"[FAIL] {name}: {type(e).__name__}: {e}")
        return False


def python_version():
    v = sys.version_info
    if v < (3, 10):
        raise RuntimeError(f"Python 3.10+ required, found {v.major}.{v.minor}")
    if ".venv" not in sys.executable:
        raise RuntimeError(f"Not running inside .venv: {sys.executable}")
    return f"{v.major}.{v.minor}.{v.micro} (inside .venv)"


def libs_check():
    import pandas, pydantic, sklearn, streamlit, sqlalchemy, pyarrow  # noqa: F401
    return "pandas, pydantic, scikit-learn, streamlit, sqlalchemy, pyarrow import fine"


def tesseract_check():
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_PATH")
    langs = pytesseract.get_languages(config="")
    if "eng" not in langs or "deu" not in langs:
        raise RuntimeError(f"Need eng and deu, found: {langs}")
    return f"Tesseract {pytesseract.get_tesseract_version()}, languages: {langs}"


def pdf_and_ocr_check():
    import pymupdf
    import pytesseract
    from PIL import Image

    pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_PATH")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Invoice 12345 Total 99.50 EUR", fontsize=24)
    direct_text = page.get_text()
    pix = page.get_pixmap(dpi=200)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    ocr_text = pytesseract.image_to_string(img, lang="eng")
    if "12345" not in direct_text:
        raise RuntimeError(f"Direct text extraction failed: {direct_text!r}")
    if "12345" not in ocr_text:
        raise RuntimeError(f"OCR failed: {ocr_text!r}")
    return f"PyMuPDF {pymupdf.VersionBind}: direct text OK, OCR OK"


def ollama_check():
    import ollama
    models = [m.model for m in ollama.list().models]
    missing = [m for m in ["qwen3:4b", "qwen2.5:3b"] if m not in models]
    if missing:
        raise RuntimeError(f"Missing models: {missing}. Installed: {models}")
    return f"models available: {models}"


def llm_json_check():
    import ollama
    from pydantic import BaseModel

    class Ping(BaseModel):
        answer: int

    resp = ollama.chat(
        model=os.getenv("OLLAMA_MODEL", "qwen3:4b"),
        messages=[{"role": "user", "content": "What is 2+2? Reply as JSON."}],
        format=Ping.model_json_schema(),
        think=False,
        options={"temperature": 0, "num_ctx": 2048},
    )
    parsed = Ping.model_validate_json(resp.message.content)
    return f"structured output parsed: {parsed}"


def postgres_check():
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import URL

    url = URL.create(
        "postgresql+psycopg",
        username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME"),
    )
    with create_engine(url).connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
    return version.split(",")[0]


if __name__ == "__main__":
    results = [
        check("Python", python_version),
        check("Libraries", libs_check),
        check("Tesseract", tesseract_check),
        check("PDF text + OCR", pdf_and_ocr_check),
        check("Ollama models", ollama_check),
        check("LLM structured JSON", llm_json_check),
        check("PostgreSQL", postgres_check),
    ]
    print()
    print("ALL CHECKS PASSED" if all(results) else "SOME CHECKS FAILED - fix before Phase 2")
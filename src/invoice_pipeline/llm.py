"""M2: extract invoice fields with a local LLM (Ollama), no validation or repair.

The model gets the invoice text and must answer in JSON that follows the
Invoice schema (Ollama's structured output). Whatever comes back is parsed as
JSON and nothing else is done to it: wrong values stay wrong, which is exactly
what M2 is meant to measure.
"""
import json
import time

from invoice_pipeline.schema import Invoice

SYSTEM_PROMPT = """You extract data from invoices. Return one JSON object that follows the given schema.
Rules:
- Use only information printed in the invoice text. Never guess or calculate values.
- If a field is not printed in the invoice, use null for it.
- supplier_name is the company that issued the invoice, not the customer ("Bill to" / "An" / "To").
- invoice_number: copy it exactly as printed, including any prefix or "#".
- Dates as YYYY-MM-DD.
- Amounts as plain numbers with a dot as decimal separator and no currency symbol or thousands separator (1.234,56 EUR -> 1234.56; $2,607.29 -> 2607.29).
- quantity as a number (1,5 -> 1.5).
- currency as a 3-letter ISO code (EUR, USD, GBP).
- subtotal is the net amount before tax; tax_amount is the tax; total_amount is the final amount to pay.
- line_items: one entry per invoice row, in order, with description, quantity, unit_price and line_total."""


def build_messages(lines: list[str]) -> list[dict]:
    text = "\n".join(lines)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Invoice text:\n\n{text}\n\nReturn the JSON object."},
    ]


def default_client():
    import ollama  # imported here so the tests do not need Ollama

    return ollama.Client()


def extract_with_llm(lines: list[str], model: str, client=None) -> dict:
    """Return {"raw", "pred", "parse_ok", "seconds"}; pred is {} if the reply is not valid JSON."""
    client = client or default_client()
    started = time.perf_counter()
    response = client.chat(
        model=model,
        messages=build_messages(lines),
        format=Invoice.model_json_schema(),
        think=False,
        options={"temperature": 0, "seed": 0, "num_ctx": 4096},
    )
    seconds = time.perf_counter() - started
    raw = response["message"]["content"]
    try:
        pred = json.loads(raw)
        parse_ok = isinstance(pred, dict)
        if not parse_ok:
            pred = {}
    except json.JSONDecodeError:
        pred, parse_ok = {}, False
    return {"raw": raw, "pred": pred, "parse_ok": parse_ok, "seconds": round(seconds, 2)}

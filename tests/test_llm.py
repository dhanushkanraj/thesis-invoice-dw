import json

from invoice_pipeline.llm import build_messages, extract_with_llm
from invoice_pipeline.schema import Invoice


class FakeClient:
    def __init__(self, content):
        self.content, self.calls = content, []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return {"message": {"content": self.content}}


def test_prompt_contains_invoice_text_and_rules():
    msgs = build_messages(["Rechnungsnummer: RE-1", "Gesamtbetrag 10,00 €"])
    assert msgs[0]["role"] == "system" and "null" in msgs[0]["content"]
    assert "Rechnungsnummer: RE-1" in msgs[1]["content"] and "Gesamtbetrag 10,00 €" in msgs[1]["content"]


def test_valid_json_is_returned_untouched():
    answer = {"invoice_number": "X", "total_amount": "oops"}  # wrong types are NOT repaired in M2
    client = FakeClient(json.dumps(answer))
    res = extract_with_llm(["a"], "qwen3:4b", client=client)
    assert res["parse_ok"] and res["pred"] == answer


def test_invalid_json_gives_empty_prediction():
    res = extract_with_llm(["a"], "m", client=FakeClient("not json {"))
    assert not res["parse_ok"] and res["pred"] == {}
    res = extract_with_llm(["a"], "m", client=FakeClient("[1, 2]"))
    assert not res["parse_ok"] and res["pred"] == {}


def test_call_uses_schema_zero_temperature_and_no_thinking():
    client = FakeClient("{}")
    extract_with_llm(["a"], "qwen3:4b", client=client)
    call = client.calls[0]
    assert call["model"] == "qwen3:4b" and call["think"] is False
    assert call["options"]["temperature"] == 0
    assert call["format"] == Invoice.model_json_schema()

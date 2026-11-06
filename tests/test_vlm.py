import numpy as np

from app.vision import vlm_ocr
from app.vision.vlm_ocr import VlmOcr


class FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


IMG = np.full((100, 200, 3), 255, dtype=np.uint8)


def test_not_configured_without_key():
    assert not VlmOcr({"enabled": True, "provider": "openai", "model": "x"}).is_configured()


def test_azure_openai_call(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json)
        return FakeResp(200, {"choices": [{"message": {"content": "Αγαπητή Μαρία,\nευχαριστώ"}}]})

    monkeypatch.setattr(vlm_ocr.requests, "post", fake_post)
    v = VlmOcr({"enabled": True, "provider": "azure_openai", "key": "k",
                "endpoint": "https://r.openai.azure.com/", "deployment": "gpt4o"})
    res = v.run(IMG)
    assert res.text == "Αγαπητή Μαρία,\nευχαριστώ"
    assert res.source == "vlm_azure_openai"
    assert captured["url"].startswith("https://r.openai.azure.com/openai/deployments/gpt4o/chat/completions")
    assert captured["headers"]["api-key"] == "k"
    assert captured["json"]["temperature"] == 0


def test_anthropic_call(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == "https://api.anthropic.com/v1/messages"
        assert json["messages"][0]["content"][0]["type"] == "image"
        return FakeResp(200, {"content": [{"type": "text", "text": "Hello"}]})

    monkeypatch.setattr(vlm_ocr.requests, "post", fake_post)
    v = VlmOcr({"enabled": True, "provider": "anthropic", "key": "k", "model": "m"})
    assert v.run(IMG).text == "Hello"


def test_no_text_marker(monkeypatch):
    monkeypatch.setattr(vlm_ocr.requests, "post",
                        lambda *a, **k: FakeResp(200, {"choices": [{"message": {"content": "NO_TEXT"}}]}))
    v = VlmOcr({"enabled": True, "provider": "openai", "key": "k", "model": "m"})
    assert v.run(IMG).text == ""


def test_http_error_returns_none(monkeypatch):
    monkeypatch.setattr(vlm_ocr.requests, "post", lambda *a, **k: FakeResp(429, {"error": "rate"}))
    v = VlmOcr({"enabled": True, "provider": "openai", "key": "k", "model": "m"})
    assert v.run(IMG) is None


def test_reasoning_model_param_retry(monkeypatch):
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(dict(json))
        if "max_tokens" in json:
            return FakeResp(400, {"error": {"code": "unsupported_parameter",
                                            "message": "Unsupported parameter: 'max_tokens'"}})
        return FakeResp(200, {"choices": [{"message": {"content": "Γεια"}}]})

    monkeypatch.setattr(vlm_ocr.requests, "post", fake_post)
    v = VlmOcr({"enabled": True, "provider": "azure_openai", "key": "k",
                "endpoint": "https://r.openai.azure.com", "deployment": "gpt-5-mini"})
    assert v.run(IMG).text == "Γεια"
    assert "max_completion_tokens" in calls[1] and "temperature" not in calls[1]

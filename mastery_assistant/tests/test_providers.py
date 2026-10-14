import io
import urllib.error

import pytest

import providers
from providers import DEFAULT_MODELS, PROVIDERS, ProviderError, ask_provider


@pytest.mark.parametrize("provider", PROVIDERS)
def test_each_provider_has_a_default_model(provider):
    assert DEFAULT_MODELS[provider]


def test_gemini_request_shape_and_frame_limit(monkeypatch):
    captured = {}
    def fake_request(url, headers, body, timeout=50):
        captured.update(url=url, headers=headers, body=body, timeout=timeout)
        return {"candidates": [{"content": {"parts": [{"text": "hello"}, {"text": " there"}]}}]}

    monkeypatch.setattr(providers, "_request_json", fake_request)
    images = ["aGVsbG8="] * 10
    answer = ask_provider("Gemini", "secret-key", DEFAULT_MODELS["Gemini"], "system", "review", images)
    assert answer == "hello\n there"
    assert len(captured["body"]["contents"][0]["parts"]) == 1 + 6
    assert "temperature" not in captured["body"]["generationConfig"]
    assert captured["headers"]["x-goog-api-key"] == "secret-key"
    assert f'{DEFAULT_MODELS["Gemini"]}:generateContent' in captured["url"]


def test_openai_request_is_text_only_when_no_images(monkeypatch):
    captured = {}
    def fake_request(url, headers, body, timeout=50):
        captured.update(url=url, headers=headers, body=body)
        return {"choices": [{"message": {"content": "summary"}}]}

    monkeypatch.setattr(providers, "_request_json", fake_request)
    assert ask_provider("OpenAI", "key", DEFAULT_MODELS["OpenAI"], "system", "review") == "summary"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["body"]["model"] == "gpt-5.4-mini"
    assert "temperature" not in captured["body"]
    assert captured["body"]["messages"][1]["content"] == "review"


def test_openrouter_headers_and_images_are_in_request(monkeypatch):
    captured = {}
    def fake_request(url, headers, body, timeout=50):
        captured.update(url=url, headers=headers, body=body)
        return {"choices": [{"message": {"content": "summary"}}]}

    monkeypatch.setattr(providers, "_request_json", fake_request)
    assert ask_provider("OpenRouter", "key", DEFAULT_MODELS["OpenRouter"], "system", "review", ["aGVsbG8="]) == "summary"
    assert captured["headers"]["HTTP-Referer"].startswith("https://github.com/")
    assert "temperature" not in captured["body"]
    assert captured["body"]["messages"][1]["content"][1]["image_url"]["url"].endswith("aGVsbG8=")


def test_anthropic_payload_and_response_omits_unsupported_sampling_settings(monkeypatch):
    captured = {}
    def fake_request(url, headers, body, timeout=50):
        captured.update(url=url, headers=headers, body=body)
        return {"content": [{"type": "text", "text": "notes"}, {"type": "image"}]}

    monkeypatch.setattr(providers, "_request_json", fake_request)
    assert ask_provider("Anthropic", "key", DEFAULT_MODELS["Anthropic"], "system", "review", ["aGVsbG8="]) == "notes"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["body"]["model"] == "claude-haiku-5-5"
    assert "temperature" not in captured["body"]
    assert "top_p" not in captured["body"]
    assert captured["body"]["messages"][0]["content"][1]["source"]["media_type"] == "image/jpeg"


@pytest.mark.parametrize(
    "provider,key,model,system,prompt,match",
    [
        ("bad", "key", "model", "", "", "supported cloud provider"),
        ("Gemini", "", "model", "", "", "API key"),
        ("Gemini", "key", "bad?query", "", "", "unsupported characters"),
        ("Gemini", "key", "google/model", "", "", "provider-specific"),
        ("Gemini", "key", "model", "", "x" * 30001, "exceeds"),
        ("Gemini", "key", "model", "x" * 8001, "", "exceeds"),
    ],
)
def test_provider_rejects_invalid_input_before_network(provider, key, model, system, prompt, match):
    with pytest.raises(ProviderError, match=match):
        ask_provider(provider, key, model, system, prompt)


def test_api_key_with_newline_is_rejected():
    with pytest.raises(ProviderError, match="single line"):
        ask_provider("Gemini", "secret\nforged-header", "gemini-test", "system", "review")


def test_oversized_image_is_rejected_before_network():
    with pytest.raises(ProviderError, match="upload size"):
        ask_provider("Gemini", "key", "gemini-test", "system", "review", ["a" * 700001])


def test_http_error_does_not_leak_response_body(monkeypatch):
    def fail_request(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://example.invalid", 401, "Unauthorized", {}, io.BytesIO(b"secret token echoed by server")
        )

    monkeypatch.setattr(providers.urllib.request, "urlopen", fail_request)
    with pytest.raises(ProviderError) as exc_info:
        providers._request_json("https://example.invalid", {}, {})
    assert "HTTP 401" in str(exc_info.value)
    assert "secret token" not in str(exc_info.value)


def test_empty_provider_response_is_reported(monkeypatch):
    monkeypatch.setattr(providers, "_request_json", lambda *args, **kwargs: {"candidates": []})
    with pytest.raises(ProviderError, match="did not return a text answer"):
        ask_provider("Gemini", "key", "gemini-test", "system", "review")

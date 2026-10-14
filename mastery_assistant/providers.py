"""Small direct-HTTPS clients for supported AI providers.

No background polling and no automatic provider fan-out. One provider is called
only when the user explicitly requests analysis.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Sequence

PROVIDERS = ("Gemini", "OpenAI", "Anthropic", "OpenRouter")
SERVICE_NAMES = {
    "Gemini": "BloxFruitsMasteryAssistant/Gemini",
    "OpenAI": "BloxFruitsMasteryAssistant/OpenAI",
    "Anthropic": "BloxFruitsMasteryAssistant/Anthropic",
    "OpenRouter": "BloxFruitsMasteryAssistant/OpenRouter",
}
DEFAULT_MODELS = {
    "Gemini": "gemini-3.5-flash-lite",
    "OpenAI": "gpt-4.1-mini",
    "Anthropic": "claude-haiku-4-5",
    "OpenRouter": "google/gemini-3.5-flash-lite",
}


class ProviderError(RuntimeError):
    pass


def _request_json(url: str, headers: dict[str, str], body: dict, timeout: int = 50) -> dict:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read(1500).decode("utf-8", errors="replace")
        raise ProviderError(f"Provider returned HTTP {exc.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderError(f"Could not reach provider: {exc}") from None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise ProviderError("Provider returned an unreadable response.") from None


def ask_provider(
    provider: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    images_b64: Sequence[str] = (),
) -> str:
    """Send a bounded text request and optional JPEG frames to one provider."""
    provider = provider.strip()
    if provider not in PROVIDERS:
        raise ProviderError("Choose a supported cloud provider.")
    if not api_key.strip():
        raise ProviderError(f"Add a {provider} API key first.")
    model = (model or DEFAULT_MODELS[provider]).strip() or DEFAULT_MODELS[provider]

    if provider == "Gemini":
        parts: list[dict] = [{"text": user_prompt}]
        parts.extend({"inlineData": {"mimeType": "image/jpeg", "data": image}} for image in images_b64)
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1100},
        }
        data = _request_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            {"Content-Type": "application/json", "x-goog-api-key": api_key.strip()},
            body,
        )
        try:
            return "\n".join(
                part.get("text", "")
                for part in data["candidates"][0]["content"]["parts"]
                if part.get("text")
            ).strip()
        except (KeyError, IndexError, TypeError):
            raise ProviderError("Gemini did not return a text answer.") from None

    if provider in ("OpenAI", "OpenRouter"):
        content: object
        if images_b64:
            content = [{"type": "text", "text": user_prompt}] + [
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + image}}
                for image in images_b64
            ]
        else:
            content = user_prompt
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            "temperature": 0.2,
            "max_tokens": 1100,
        }
        url = (
            "https://api.openai.com/v1/chat/completions"
            if provider == "OpenAI"
            else "https://openrouter.ai/api/v1/chat/completions"
        )
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key.strip()}"}
        if provider == "OpenRouter":
            headers["HTTP-Referer"] = "https://github.com/dragonballls/virtual-keyboard-and-mouse"
            headers["X-Title"] = "Blox Fruits Mastery Assistant"
        data = _request_json(url, headers, body)
        try:
            choice = data["choices"][0]["message"]["content"]
            if isinstance(choice, str):
                return choice.strip()
            if isinstance(choice, list):
                return "\n".join(p.get("text", "") for p in choice if isinstance(p, dict)).strip()
        except (KeyError, IndexError, TypeError):
            pass
        raise ProviderError(f"{provider} did not return a text answer.")

    content_parts: list[dict] = [{"type": "text", "text": user_prompt}]
    content_parts.extend(
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": image},
        }
        for image in images_b64
    )
    data = _request_json(
        "https://api.anthropic.com/v1/messages",
        {
            "Content-Type": "application/json",
            "x-api-key": api_key.strip(),
            "anthropic-version": "2023-06-01",
        },
        {
            "model": model,
            "max_tokens": 1100,
            "temperature": 0.2,
            "system": system_prompt,
            "messages": [{"role": "user", "content": content_parts}],
        },
    )
    try:
        return "\n".join(part.get("text", "") for part in data["content"] if part.get("type") == "text").strip()
    except (KeyError, TypeError):
        raise ProviderError("Anthropic did not return a text answer.") from None

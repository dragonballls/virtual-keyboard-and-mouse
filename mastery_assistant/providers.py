"""Small direct-HTTPS clients for supported AI providers.

No background polling or automatic provider fan-out occurs. One provider is called
only when the user explicitly requests a bounded review.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Sequence
from urllib.parse import quote

PROVIDERS = ("Gemini", "OpenAI", "Anthropic", "OpenRouter")
SERVICE_NAMES = {
    "Gemini": "BloxFruitsMasteryAssistant/Gemini",
    "OpenAI": "BloxFruitsMasteryAssistant/OpenAI",
    "Anthropic": "BloxFruitsMasteryAssistant/Anthropic",
    "OpenRouter": "BloxFruitsMasteryAssistant/OpenRouter",
}
DEFAULT_MODELS = {
    "Gemini": "gemini-3.5-flash-lite",
    "OpenAI": "gpt-5.4-mini",
    "Anthropic": "claude-haiku-5-5",
    "OpenRouter": "google/gemini-3.5-flash-lite",
}
MAX_IMAGES = 6
MAX_IMAGE_BASE64_CHARS = 700_000
MAX_SYSTEM_PROMPT_CHARS = 8_000
MAX_USER_PROMPT_CHARS = 30_000
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,119}$")


class ProviderError(RuntimeError):
    pass


def _request_json(url: str, headers: dict[str, str], body: dict, timeout: int = 50) -> dict:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        # Do not display raw server bodies: some providers include request metadata.
        hints = {
            400: "Check the model name and request format.",
            401: "Check the API key.",
            403: "Check the API key and project permissions.",
            404: "Check whether the selected model is available to this endpoint.",
            429: "The provider rate limit or quota may have been reached.",
        }
        hint = hints.get(exc.code, "Check the provider status and try again later.")
        raise ProviderError(f"Provider returned HTTP {exc.code}. {hint}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProviderError("Could not reach the provider. Check your connection and try again.") from None
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise ProviderError("Provider returned an unreadable response.") from None
    if not isinstance(result, dict):
        raise ProviderError("Provider returned an unexpected response format.")
    return result


def ask_provider(
    provider: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    images_b64: Sequence[str] = (),
) -> str:
    """Send a bounded text request and optional JPEG frames to one provider."""
    provider = str(provider or "").strip()
    if provider not in PROVIDERS:
        raise ProviderError("Choose a supported cloud provider.")
    api_key = str(api_key or "").strip()
    if not api_key:
        raise ProviderError(f"Add a {provider} API key first.")
    if "\r" in api_key or "\n" in api_key:
        raise ProviderError("The API key must be a single line.")

    model = str(model or DEFAULT_MODELS[provider]).strip() or DEFAULT_MODELS[provider]
    if not _MODEL_RE.fullmatch(model):
        raise ProviderError("The model name contains unsupported characters.")
    if "/" in model and provider != "OpenRouter":
        raise ProviderError("Use a provider-specific model name for this provider.")
    system_prompt = str(system_prompt or "")
    user_prompt = str(user_prompt or "")
    if len(system_prompt) > MAX_SYSTEM_PROMPT_CHARS:
        raise ProviderError(f"The system prompt exceeds {MAX_SYSTEM_PROMPT_CHARS} characters.")
    if len(user_prompt) > MAX_USER_PROMPT_CHARS:
        raise ProviderError(f"The user prompt exceeds {MAX_USER_PROMPT_CHARS} characters.")

    frames: list[str] = []
    try:
        for index, image in enumerate(images_b64 or ()):
            if index >= MAX_IMAGES:
                break
            if not isinstance(image, str) or not image:
                raise ProviderError("Image frames must be non-empty base64 strings.")
            if len(image) > MAX_IMAGE_BASE64_CHARS:
                raise ProviderError("An image frame exceeds the allowed upload size.")
            frames.append(image)
    except TypeError:
        raise ProviderError("Image frames must be supplied as a sequence.") from None

    if provider == "Gemini":
        parts: list[dict] = [{"text": user_prompt}]
        parts.extend({"inlineData": {"mimeType": "image/jpeg", "data": image}} for image in frames)
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"maxOutputTokens": 1100},
        }
        encoded_model = quote(model, safe="._-")
        data = _request_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{encoded_model}:generateContent",
            {"Content-Type": "application/json", "x-goog-api-key": api_key},
            body,
        )
        try:
            answer = "\n".join(
                part.get("text", "")
                for part in data["candidates"][0]["content"]["parts"]
                if isinstance(part, dict) and part.get("text")
            ).strip()
        except (KeyError, IndexError, TypeError):
            answer = ""
        if answer:
            return answer
        raise ProviderError("Gemini did not return a text answer.")

    if provider in ("OpenAI", "OpenRouter"):
        content: object
        if frames:
            content = [{"type": "text", "text": user_prompt}] + [
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + image}}
                for image in frames
            ]
        else:
            content = user_prompt
        token_limit = {"max_completion_tokens": 1100} if provider == "OpenAI" else {"max_tokens": 1100}
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            **token_limit,
        }
        url = (
            "https://api.openai.com/v1/chat/completions"
            if provider == "OpenAI"
            else "https://openrouter.ai/api/v1/chat/completions"
        )
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        if provider == "OpenRouter":
            headers["HTTP-Referer"] = "https://github.com/dragonballls/virtual-keyboard-and-mouse"
            headers["X-Title"] = "Blox Fruits Mastery Assistant"
        data = _request_json(url, headers, body)
        try:
            choice = data["choices"][0]["message"]["content"]
            if isinstance(choice, str) and choice.strip():
                return choice.strip()
            if isinstance(choice, list):
                answer = "\n".join(
                    part["text"] for part in choice
                    if isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"]
                ).strip()
                if answer:
                    return answer
        except (KeyError, IndexError, TypeError):
            pass
        raise ProviderError(f"{provider} did not return a text answer.")

    content_parts: list[dict] = [{"type": "text", "text": user_prompt}]
    content_parts.extend(
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": image},
        }
        for image in frames
    )
    data = _request_json(
        "https://api.anthropic.com/v1/messages",
        {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        {
            "model": model,
            "max_tokens": 1100,
            "system": system_prompt,
            "messages": [{"role": "user", "content": content_parts}],
        },
    )
    try:
        answer = "\n".join(
            part.get("text", "")
            for part in data["content"]
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text")
        ).strip()
    except (KeyError, TypeError):
        answer = ""
    if answer:
        return answer
    raise ProviderError("Anthropic did not return a text answer.")

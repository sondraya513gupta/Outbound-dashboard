import json
import re
from typing import Any

import httpx

from config import OPENROUTER_API_KEY, OPENROUTER_BASE, OPENROUTER_MODEL

WEB_SEARCH_TOOL = {
    "type": "openrouter:web_search",
    "parameters": {
        "engine": "auto",
        "max_results": 8,
        "max_uses": 4,
        "search_context_size": "medium",
    },
}


class OpenRouterError(RuntimeError):
    pass


async def chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.3,
    json_mode: bool = False,
    use_web: bool = False,
    timeout: float = 90.0,
) -> str:
    if not OPENROUTER_API_KEY:
        raise OpenRouterError("OPENROUTER_API_KEY is missing. Add it to .env")

    payload: dict[str, Any] = {
        "model": model or OPENROUTER_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if use_web:
        payload["tools"] = [WEB_SEARCH_TOOL]

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "Upthrust Outbound Desk",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{OPENROUTER_BASE}/chat/completions",
            headers=headers,
            json=payload,
        )
        if response.status_code >= 400:
            raise OpenRouterError(
                f"OpenRouter {response.status_code}: {response.text[:400]}"
            )
        data = response.json()

    choices = data.get("choices") or []
    if not choices:
        raise OpenRouterError(f"OpenRouter returned no choices: {data}")
    content = choices[0].get("message", {}).get("content") or ""
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return content.strip()


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        return {"items": parsed}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise OpenRouterError("Model did not return JSON")
        parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            return {"items": parsed}
        return parsed

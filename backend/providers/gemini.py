import json
import logging
import os
import time

import httpx

from .base import AIProvider

logger = logging.getLogger(__name__)


class GeminiProvider(AIProvider):

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    async def generate(self, messages, model=None, **kwargs):
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        model = model or "gemini-2.5-flash"

        contents = []

        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")

            if role == "system":
                contents.append({
                    "role": "user",
                    "parts": [{"text": content}]
                })
            else:
                contents.append({
                    "role": "model" if role == "assistant" else "user",
                    "parts": [{"text": content}]
                })

        url = f"{self.base_url}/models/{model}:generateContent"

        payload = {
            "contents": contents,
            **kwargs,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url,
                params={"key": self.api_key},
                json=payload,
            )

        response.raise_for_status()

        data = response.json()

        return data["candidates"][0]["content"]["parts"][0]["text"]

    def _request_kwargs(self, kwargs):
        # The chat handler passes OpenAI-style options
        # (max_tokens, chat_template_kwargs). Map the ones Gemini
        # understands into generationConfig and drop the rest.
        generation_config = {}

        if "temperature" in kwargs:
            generation_config["temperature"] = kwargs["temperature"]

        if "max_tokens" in kwargs:
            generation_config["maxOutputTokens"] = kwargs["max_tokens"]

        return generation_config

    async def generate_stream(self, messages, model=None, **kwargs):
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

        contents = []
        system_parts = []

        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")

            if role == "system":
                system_parts.append(content)
            else:
                contents.append({
                    "role": "model" if role == "assistant" else "user",
                    "parts": [{"text": content}],
                })

        payload = {
            "contents": contents,
            "generationConfig": self._request_kwargs(kwargs),
        }

        if system_parts:
            payload["systemInstruction"] = {
                "parts": [{"text": "\n\n".join(system_parts)}],
            }

        url = f"{self.base_url}/models/{model}:streamGenerateContent"

        first_chunk_logged = False
        request_start = time.perf_counter()

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                url,
                # httpx replaces the URL query when params is set,
                # so alt=sse must travel here too, not in the URL.
                params={
                    "key": self.api_key,
                    "alt": "sse",
                },
                json=payload,
            ) as response:
                logger.info(
                    "Gemini stream headers: status=%d in %.2fs",
                    response.status_code,
                    time.perf_counter() - request_start,
                )

                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue

                    if isinstance(data, list):
                        data = data[0] if data else {}

                    for part in (
                        data.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [])
                    ):
                        text = part.get("text")

                        if text:
                            if not first_chunk_logged:
                                first_chunk_logged = True

                                logger.info(
                                    "Gemini first content chunk: %.2fs",
                                    time.perf_counter() - request_start,
                                )

                            yield text

        logger.info(
            "Gemini stream completed: %.2fs",
            time.perf_counter() - request_start,
        )

    async def health_check(self):
        if not self.api_key:
            return False

        url = f"{self.base_url}/models"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    params={"key": self.api_key},
                )

            return response.is_success

        except Exception:
            return False
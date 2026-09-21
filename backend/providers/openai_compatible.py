import json
import time
import logging
import httpx

from backend.providers.base import AIProvider


logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(AIProvider):
    def __init__(self, name, base_url, api_key):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def generate(self, messages, model=None, **kwargs):
        if not self.api_key:
            raise ValueError(f"API key not configured for {self.name}")

        payload = {
            "messages": messages,
            **kwargs,
        }

        if model:
            payload["model"] = model

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=10.0)
        ) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )

            response.raise_for_status()

            data = response.json()

            return data["choices"][0]["message"]["content"]

    async def generate_stream(self, messages, model=None, **kwargs):
        if not self.api_key:
            raise ValueError(f"API key not configured for {self.name}")

        payload = {
            "messages": messages,
            "stream": True,
            **kwargs,
        }

        if model:
            payload["model"] = model

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        request_start = time.perf_counter()
        first_chunk_received = False

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=10.0)
        ) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:

                logger.info(
                    "NVIDIA response headers: %.2fs",
                    time.perf_counter() - request_start,
                )

                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    if line.startswith("data: "):
                        data = line[6:]

                        if data == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data)

                            content = (
                                chunk["choices"][0]
                                .get("delta", {})
                                .get("content")
                            )

                            if content:
                                if not first_chunk_received:
                                    first_chunk_received = True

                                    logger.info(
                                        "NVIDIA first content chunk: %.2fs",
                                        time.perf_counter() - request_start,
                                    )

                                yield content

                        except json.JSONDecodeError:
                            continue

                logger.info(
                    "NVIDIA stream completed: %.2fs",
                    time.perf_counter() - request_start,
                )

    async def ping(self):
        """
        Live reachability check (GET /models).

        Any HTTP response means the endpoint is
        reachable; authentication failures surface
        as raise_for_status errors.
        """

        if not self.api_key:
            return {
                "reachable": False,
                "detail": "API key not configured",
            }

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
            }

            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=headers,
                )

                response.raise_for_status()

            return {
                "reachable": True,
                "status_code": response.status_code,
            }

        except httpx.HTTPError as error:
            return {
                "reachable": False,
                "detail": type(error).__name__,
            }

    async def health_check(self):
        return bool(self.api_key)
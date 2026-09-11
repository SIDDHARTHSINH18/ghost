import json
import httpx

from providers.base import AIProvider


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

        async with httpx.AsyncClient(timeout=120) as client:
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

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:

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
                                yield content

                        except json.JSONDecodeError:
                            continue

    async def health_check(self):
        return bool(self.api_key)
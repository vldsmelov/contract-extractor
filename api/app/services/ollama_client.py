from typing import Optional

import httpx
from httpx import HTTPStatusError
from ..core.config import CONFIG

class OllamaClient:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = base_url or CONFIG.ollama_host
        self.model = model or CONFIG.model_name

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        options = {
            "temperature": temperature if temperature is not None else CONFIG.temperature,
            "num_predict": max_tokens if max_tokens is not None else CONFIG.max_tokens,
        }

        timeout = httpx.Timeout(connect=10.0, read=CONFIG.ollama_read_timeout)

        async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
            chat_payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": options,
            }

            try:
                response = await client.post("/api/chat", json=chat_payload)
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "")
            except httpx.ReadTimeout as exc:
                raise RuntimeError(
                    "Timed out waiting for a response from the Ollama service. "
                    "Consider increasing OLLAMA_READ_TIMEOUT or checking the model performance."
                ) from exc
            except HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise

            # Fallback для старых версий Ollama без /api/chat
            generate_payload = {
                "model": self.model,
                "system": system_prompt,
                "prompt": user_prompt,
                "stream": False,
                "options": options,
            }

            response = await client.post("/api/generate", json=generate_payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")

    async def list_models(self):
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
            r = await client.get("/api/tags")
            r.raise_for_status()
            return r.json()

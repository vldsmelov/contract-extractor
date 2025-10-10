import httpx
from typing import Dict, Any, Optional, List
from ..core.config import CONFIG

class OllamaClient:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = base_url or CONFIG.ollama_host
        self.model = model or CONFIG.model_name

    async def chat(self, system_prompt: str, user_prompt: str, temperature: float = None, max_tokens: int = None) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": temperature if temperature is not None else CONFIG.temperature,
                "num_predict": max_tokens if max_tokens is not None else CONFIG.max_tokens
            }
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=120.0) as client:
            r = await client.post("/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
            # Ollama returns {"message":{"content": "..."}}
            msg = data.get("message", {}).get("content", "")
            return msg

    async def list_models(self):
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
            r = await client.get("/api/tags")
            r.raise_for_status()
            return r.json()

import json
from pathlib import Path
from typing import Dict, Any
from .base import BaseExtractor
from ..ollama_client import OllamaClient
from ...core.config import CONFIG

class LLMExtractor(BaseExtractor):
    def __init__(self, schema: Dict[str, Any], system_path: str, user_tmpl_path: str):
        self.schema = schema
        self.system_prompt = Path(system_path).read_text(encoding="utf-8")
        self.user_template = Path(user_tmpl_path).read_text(encoding="utf-8")
        self.client = OllamaClient()

    async def extract(self, text: str, partial: Dict[str, Any]) -> Dict[str, Any]:
        # Встраиваем схему внутрь промпта
        user_prompt = self.user_template.format(
            document_text=text[:100000],  # безопасный лимит
            json_schema=json.dumps(self.schema, ensure_ascii=False, indent=2)
        )
        raw = await self.client.chat(self.system_prompt, user_prompt, temperature=CONFIG.temperature, max_tokens=CONFIG.max_tokens)

        # Попытка распарсить JSON напрямую
        data = None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Попробуем выделить JSON по границам
            import re
            m = re.search(r"\{[\s\S]*\}", raw)
            if m:
                try:
                    data = json.loads(m.group(0))
                except Exception:
                    data = {}

        if not isinstance(data, dict):
            data = {}

        # Не перетираем уже найденные правилами поля
        merged = dict(data)
        merged.update(partial)  # приоритет у правил/локальной логики
        return merged

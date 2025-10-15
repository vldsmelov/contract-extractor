import json
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Any

from .base import BaseExtractor
from ..ollama_client import OllamaClient
from ..normalize import normalize_whitespace
from app.core.config import CONFIG


class LLMExtractor(BaseExtractor):
    def __init__(
        self,
        schema: Dict[str, Any],
        system_path: str,
        user_tmpl_path: str,
        field_guidelines_path: str | None = None,
        field_guidelines: str | None = None,
    ):
        self.schema = schema
        self.system_prompt = Path(system_path).read_text(encoding="utf-8")
        self.user_template = Path(user_tmpl_path).read_text(encoding="utf-8")
        if field_guidelines is not None:
            self.field_guidelines = field_guidelines
        elif field_guidelines_path and Path(field_guidelines_path).exists():
            self.field_guidelines = Path(field_guidelines_path).read_text(encoding="utf-8")
        else:
            self.field_guidelines = ""
        self.client = OllamaClient()
        self.last_prompt: str = ""
        self.last_raw: str = ""

    async def extract(
        self,
        text: str,
        partial: Dict[str, Any],
        *,
        schema_override: Dict[str, Any] | None = None,
        field_guidelines: str | None = None,
    ) -> Dict[str, Any]:
        schema_to_use = schema_override or self.schema
        guidelines_to_use = field_guidelines if field_guidelines is not None else self.field_guidelines
        json_schema = json.dumps(schema_to_use, ensure_ascii=False, indent=2)
        json_skeleton = json.dumps(
            self._build_json_skeleton(schema_to_use), ensure_ascii=False, indent=2
        )

        # Встраиваем схему внутрь промпта
        user_prompt = self.user_template.format(
            document_text=text[:100000],  # безопасный лимит
            json_schema=json_schema,
            json_skeleton=json_skeleton,
            field_guidelines=guidelines_to_use,
        )
        self.last_prompt = normalize_whitespace(user_prompt)
        raw = await self.client.chat(
            self.system_prompt,
            user_prompt,
            temperature=CONFIG.temperature,
            max_tokens=CONFIG.max_tokens,
        )
        self.last_raw = raw

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

    def _build_json_skeleton(self, schema: Dict[str, Any] | None = None) -> Dict[str, Any]:
        schema = schema or self.schema
        skeleton: "OrderedDict[str, Any]" = OrderedDict()
        properties: Dict[str, Any] = schema.get("properties", {})
        for key, meta in properties.items():
            type_ = meta.get("type")
            if type_ == "integer":
                skeleton[key] = 0
            elif type_ == "number":
                skeleton[key] = 0.0
            elif type_ == "boolean":
                skeleton[key] = False
            else:
                skeleton[key] = ""
        return skeleton

    def update_field_guidelines(self, guidelines: str | None) -> None:
        self.field_guidelines = guidelines or ""

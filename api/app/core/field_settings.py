from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Iterable
import json


class FieldSettings:
    """Загружает конфигурацию способов извлечения и текстовые подсказки для полей."""

    def __init__(
        self,
        extractors_path: str,
        guidelines_path: str,
        prompts_dir: str,
    ) -> None:
        self._extractors_path = Path(extractors_path)
        self._guidelines_path = Path(guidelines_path)
        self._prompts_dir = Path(prompts_dir)

        if not self._extractors_path.exists():
            raise FileNotFoundError(f"Не найден файл конфигурации полей: {self._extractors_path}")

        with self._extractors_path.open("r", encoding="utf-8") as fh:
            self._extractors: Dict[str, str] = json.load(fh)

        self._general_guidelines = (
            self._guidelines_path.read_text(encoding="utf-8")
            if self._guidelines_path.exists()
            else ""
        )

        self._field_prompts: Dict[str, str] = {}
        if self._prompts_dir.exists():
            for file in sorted(self._prompts_dir.glob("*.md")):
                self._field_prompts[file.stem] = file.read_text(encoding="utf-8")

    @property
    def extractors(self) -> Dict[str, str]:
        return self._extractors

    def get_method(self, field: str) -> str:
        return self._extractors.get(field, "LLM")

    def is_enabled(self, field: str) -> bool:
        return self.get_method(field).lower() != "off"

    def enabled_fields(self) -> Iterable[str]:
        return (field for field, method in self._extractors.items() if method.lower() != "off")

    def disabled_fields(self) -> Iterable[str]:
        return (field for field, method in self._extractors.items() if method.lower() == "off")

    def build_guidelines_bundle(self) -> str:
        sections = [self._general_guidelines.strip()] if self._general_guidelines else []

        for field, method in self._extractors.items():
            prompt = self._field_prompts.get(field, "")
            header = f"## {field} (способ: {method})"
            if prompt:
                body = prompt.strip()
            else:
                body = "Нет специальных инструкций. Используй общий контекст документа."
            sections.append(f"{header}\n\n{body}")

        return "\n\n".join(section for section in sections if section)

    def apply_to_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Возвращает копию схемы, очищенную от отключённых полей."""
        from copy import deepcopy

        filtered = deepcopy(schema)
        properties = filtered.get("properties", {})
        for field in list(properties.keys()):
            if not self.is_enabled(field):
                properties.pop(field, None)

        required_fields = filtered.get("required")
        if isinstance(required_fields, list):
            filtered["required"] = [field for field in required_fields if self.is_enabled(field)]

        return filtered

    def filter_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {key: value for key, value in payload.items() if self.is_enabled(key)}


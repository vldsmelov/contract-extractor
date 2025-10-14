from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Iterable, Iterator, Sequence
import json


@dataclass(frozen=True)
class DocumentSlice:
    mode: str = "full"
    size: int | None = None
    start: int | None = None
    end: int | None = None

    @staticmethod
    def from_dict(data: Dict[str, Any] | None) -> "DocumentSlice":
        if not data:
            return DocumentSlice()

        mode = data.get("mode")
        if mode is None:
            if "start" in data or "end" in data:
                mode = "range"
            elif "size" in data:
                # Если указан только размер, по умолчанию работаем с хвостом документа
                mode = "tail"
            else:
                mode = "full"

        mode = str(mode).lower()
        if mode not in {"full", "head", "tail", "range"}:
            raise ValueError(f"Unsupported document slice mode: {mode}")

        size = data.get("size")
        start = data.get("start")
        end = data.get("end")

        if size is not None:
            size = int(size)
            if size <= 0:
                raise ValueError("Slice size must be positive")

        if start is not None:
            start = int(start)
        if end is not None:
            end = int(end)

        return DocumentSlice(mode=mode, size=size, start=start, end=end)

    def extract(self, text: str) -> str:
        if not text:
            return text

        if self.mode == "head":
            if self.size is None:
                return text
            return text[: self.size]
        if self.mode == "tail":
            if self.size is None:
                return text
            return text[-self.size :]
        if self.mode == "range":
            start = self.start or 0
            end = self.end if self.end is not None else len(text)
            return text[start:end]
        return text


@dataclass
class LLMFieldGroup:
    fields: tuple[str, ...]
    document_slice: DocumentSlice


class FieldSettings:
    """Загружает конфигурацию способов извлечения и текстовые подсказки для полей."""

    def __init__(
        self,
        extractors_path: str,
        guidelines_path: str,
        prompts_dir: str,
        contexts_path: str | None = None,
    ) -> None:
        self._extractors_path = Path(extractors_path)
        self._guidelines_path = Path(guidelines_path)
        self._prompts_dir = Path(prompts_dir)
        self._contexts_path = Path(contexts_path) if contexts_path else None

        if not self._extractors_path.exists():
            raise FileNotFoundError(f"Не найден файл конфигурации полей: {self._extractors_path}")

        with self._extractors_path.open("r", encoding="utf-8") as fh:
            self._extractors: Dict[str, str] = json.load(fh)

        self._general_guidelines_cache: str | None = None
        self._field_prompts_cache: Dict[str, str] | None = None
        self._context_rules: Dict[str, DocumentSlice] = {}
        self._context_groups: list[LLMFieldGroup] = []
        self._load_context_rules()

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

    def build_guidelines_bundle(self, fields: Iterable[str] | None = None) -> str:
        general_guidelines = self._load_general_guidelines().strip()
        if general_guidelines:
            sections = [general_guidelines]
        else:
            sections = []

        field_prompts = self._load_field_prompts()

        if fields is None:
            iterable: Iterator[str] = (
                field
                for field in self._extractors.keys()
                if self.is_enabled(field)
            )
        else:
            iterable = (field for field in fields if self.is_enabled(field))

        for field in iterable:
            method = self._extractors.get(field, "LLM")
            prompt = field_prompts.get(field, "")
            header = f"## {field} (способ: {method})"
            if prompt:
                body = prompt.strip()
            else:
                body = "Нет специальных инструкций. Используй общий контекст документа."
            sections.append(f"{header}\n\n{body}")

        return "\n\n".join(section for section in sections if section)

    def _load_general_guidelines(self) -> str:
        if self._general_guidelines_cache is not None:
            return self._general_guidelines_cache
        if self._guidelines_path.exists():
            self._general_guidelines_cache = self._guidelines_path.read_text(encoding="utf-8")
        else:
            self._general_guidelines_cache = ""
        return self._general_guidelines_cache

    def _load_field_prompts(self) -> Dict[str, str]:
        if self._field_prompts_cache is not None:
            return self._field_prompts_cache

        prompts: Dict[str, str] = {}
        if self._prompts_dir.exists():
            for file in sorted(self._prompts_dir.glob("*.md")):
                prompts[file.stem] = file.read_text(encoding="utf-8")

        self._field_prompts_cache = prompts
        return prompts

    def refresh_prompts(self) -> None:
        """Сбрасывает кеш подсказок и перечитывает файлы."""
        self._general_guidelines_cache = None
        self._field_prompts_cache = None

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

    def llm_fields(self) -> Iterable[str]:
        return (
            field
            for field, method in self._extractors.items()
            if self.is_enabled(field) and method.lower() == "llm"
        )

    def build_llm_groups(self) -> Sequence[LLMFieldGroup]:
        if self._context_groups:
            collected: list[LLMFieldGroup] = []
            assigned: set[str] = set()
            for group in self._context_groups:
                fields = tuple(
                    field
                    for field in group.fields
                    if self.is_enabled(field)
                    and self.get_method(field).lower() == "llm"
                )
                if not fields:
                    continue
                collected.append(
                    LLMFieldGroup(fields=fields, document_slice=group.document_slice)
                )
                assigned.update(fields)

            for field in self._extractors.keys():
                if field in assigned:
                    continue
                if not self.is_enabled(field):
                    continue
                if self.get_method(field).lower() != "llm":
                    continue
                rule = self.get_context_rule(field)
                collected.append(LLMFieldGroup(fields=(field,), document_slice=rule))

            return collected

        groups: "OrderedDict[DocumentSlice, list[str]]" = OrderedDict()
        for field in self._extractors.keys():
            if not self.is_enabled(field):
                continue
            if self.get_method(field).lower() != "llm":
                continue
            rule = self.get_context_rule(field)
            if rule not in groups:
                groups[rule] = []
            groups[rule].append(field)

        return [
            LLMFieldGroup(fields=tuple(fields), document_slice=rule)
            for rule, fields in groups.items()
            if fields
        ]

    def get_context_rule(self, field: str) -> DocumentSlice:
        return self._context_rules.get(field, DocumentSlice())

    def _load_context_rules(self) -> None:
        self._context_rules = {}
        self._context_groups = []
        if not self._contexts_path or not self._contexts_path.exists():
            return

        with self._contexts_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)

        groups_data: Sequence[Dict[str, Any]] | None = None
        if isinstance(raw, dict) and "groups" in raw:
            maybe_groups = raw.get("groups", [])
            if isinstance(maybe_groups, list):
                groups_data = [item for item in maybe_groups if isinstance(item, dict)]
        elif isinstance(raw, list):
            groups_data = [item for item in raw if isinstance(item, dict)]

        if groups_data is not None:
            for item in groups_data:
                fields = item.get("fields")
                if not fields:
                    continue
                if not isinstance(fields, (list, tuple)):
                    raise ValueError("Context group 'fields' must be a list of field names")

                slice_dict = item.get("slice")
                if slice_dict is None:
                    slice_dict = {
                        key: value
                        for key, value in item.items()
                        if key not in {"fields", "name", "slice"}
                    }
                document_slice = DocumentSlice.from_dict(slice_dict)
                group = LLMFieldGroup(
                    fields=tuple(str(field) for field in fields),
                    document_slice=document_slice,
                )
                self._context_groups.append(group)
                for field in group.fields:
                    self._context_rules[field] = document_slice
            return

        if not isinstance(raw, dict):
            raise ValueError("Invalid context configuration format")

        context_rules: Dict[str, DocumentSlice] = {}
        for field, data in raw.items():
            try:
                context_rules[str(field)] = DocumentSlice.from_dict(data)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid context configuration for field '{field}': {exc}"
                ) from exc

        self._context_rules = context_rules

    def build_schema_subset(self, schema: Dict[str, Any], fields: Iterable[str]) -> Dict[str, Any]:
        from copy import deepcopy

        allowed = set(fields)
        subset = deepcopy(schema)
        properties = subset.get("properties", {})
        for field in list(properties.keys()):
            if field not in allowed:
                properties.pop(field, None)

        required = subset.get("required")
        if isinstance(required, list):
            subset["required"] = [field for field in required if field in allowed]

        return subset

from typing import Dict, Any, List, Optional
from .rules import RuleBasedExtractor
from .llm import LLMExtractor
from app.core.validator import SchemaValidator
from app.core.config import CONFIG
from app.core.field_settings import FieldSettings
from ..warnings import WarningItem
from ..normalize import normalize_whitespace
from ..summary import build_short_summary

class ExtractionPipeline:
    def __init__(
        self,
        schema: Dict[str, Any],
        system_prompt_path: str,
        user_tmpl_path: str,
        field_settings: FieldSettings,
        field_guidelines_path: Optional[str] = None,
    ):
        self.field_settings = field_settings
        self.schema = self.field_settings.apply_to_schema(schema)
        self.validator = SchemaValidator(self.schema)
        self.rules = RuleBasedExtractor()
        self.llm = None
        if CONFIG.use_llm:
            self.llm = LLMExtractor(
                self.schema,
                system_prompt_path,
                user_tmpl_path,
                field_guidelines_path,
            )

    async def run(self, text: str) -> (
        Dict[str, Any],
        List[WarningItem],
        List[Dict[str, Any]],
        Dict[str, Any],
        str,
    ):
        warnings = []

        cleaned_text = normalize_whitespace(text)

        # 1) Правила
        partial = await self.rules.extract(cleaned_text, {})

        # 2) LLM (если включен)
        prompt = ""
        raw_outputs: List[str] = []
        if self.llm is not None:
            self.field_settings.refresh_prompts()
            aggregated = dict(partial)
            prompts: List[str] = []
            for group in self.field_settings.build_llm_groups():
                schema_subset = self.field_settings.build_schema_subset(
                    self.schema, group.fields
                )
                guidelines = self.field_settings.build_guidelines_bundle(group.fields)
                segment = group.document_slice.extract(cleaned_text)
                group_partial = {
                    key: aggregated[key]
                    for key in group.fields
                    if key in aggregated
                }
                llm_result = await self.llm.extract(
                    segment,
                    group_partial,
                    schema_override=schema_subset,
                    field_guidelines=guidelines,
                )
                for field in group.fields:
                    if field in llm_result:
                        aggregated[field] = llm_result[field]
                if self.llm.last_prompt:
                    prompts.append(self.llm.last_prompt)
                if getattr(self.llm, "last_raw", ""):
                    raw_outputs.append(self.llm.last_raw)
            data = aggregated
            prompt = "\n\n-----\n\n".join(prompts)
        else:
            data = partial

        # 3) Валидация
        filtered_data = self.field_settings.filter_payload(data)
        errors = self.validator.validate(filtered_data)

        summary_text = build_short_summary(filtered_data, cleaned_text)
        if summary_text:
            filtered_data["КраткоеСодержание"] = summary_text

        # 4) Дополнительные предупреждения (пример: расхождение НДС)
        try:
            vat = float(data.get("СуммаНДС")) if data.get("СуммаНДС") is not None else None
            total = float(data.get("Сумма")) if data.get("Сумма") is not None else None
            rate = float(data.get("СтавкаНДС")) if data.get("СтавкаНДС") is not None else None
            if vat is not None and total is not None and rate is not None and rate > 0:
                expected_vat = round(total * rate / (100 + rate), 2)
                if abs(expected_vat - vat) > 0.1:
                    warnings.append(WarningItem(code="vat_mismatch", message=f"НДС в документе {vat}, расчётное значение {expected_vat} при ставке {rate}%"))
        except Exception:
            pass

        debug = {
            "disabled_fields": ", ".join(sorted(self.field_settings.disabled_fields())),
            "llm_raw_outputs": raw_outputs,
        }

        prompt = normalize_whitespace(prompt) if prompt else ""

        return filtered_data, warnings, errors, debug, prompt

from typing import Dict, Any, List, Optional
from .rules import RuleBasedExtractor
from .llm import LLMExtractor
from app.core.validator import SchemaValidator
from app.core.config import CONFIG
from app.core.field_settings import FieldSettings
from ..warnings import WarningItem

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
        guidelines_bundle = self.field_settings.build_guidelines_bundle()
        self.llm = None
        if CONFIG.use_llm:
            self.llm = LLMExtractor(
                self.schema,
                system_prompt_path,
                user_tmpl_path,
                field_guidelines_path,
                guidelines_bundle,
            )

    async def run(self, text: str) -> (
        Dict[str, Any],
        List[WarningItem],
        List[Dict[str, Any]],
        Dict[str, Any],
    ):
        warnings = []

        # 1) Правила
        partial = await self.rules.extract(text, {})

        # 2) LLM (если включен)
        if self.llm is not None:
            data = await self.llm.extract(text, partial)
        else:
            data = partial

        # 3) Валидация
        filtered_data = self.field_settings.filter_payload(data)
        errors = self.validator.validate(filtered_data)

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
            "disabled_fields": ", ".join(sorted(self.field_settings.disabled_fields()))
        }

        return filtered_data, warnings, errors, debug

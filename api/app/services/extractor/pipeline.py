from typing import Dict, Any, List, Optional
from .base import BaseExtractor
from .rules import RuleBasedExtractor
from .llm import LLMExtractor
from app.core.validator import SchemaValidator
from app.core.config import CONFIG
from ..warnings import WarningItem

class ExtractionPipeline:
    def __init__(
        self,
        schema: Dict[str, Any],
        system_prompt_path: str,
        user_tmpl_path: str,
        field_guidelines_path: Optional[str] = None,
    ):
        self.schema = schema
        self.validator = SchemaValidator(schema)
        self.rules = RuleBasedExtractor()
        self.llm = (
            LLMExtractor(schema, system_prompt_path, user_tmpl_path, field_guidelines_path)
            if CONFIG.use_llm
            else None
        )

    async def run(self, text: str) -> (Dict[str, Any], List[WarningItem], List[Dict[str, Any]]):
        warnings = []

        # 1) Правила
        partial = await self.rules.extract(text, {})

        # 2) LLM (если включен)
        if self.llm is not None:
            data = await self.llm.extract(text, partial)
        else:
            data = partial

        # 3) Валидация
        errors = self.validator.validate(data)

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

        return data, warnings, errors

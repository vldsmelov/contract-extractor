from typing import Dict, Any, List, Optional
from .rules import RuleBasedExtractor
from .llm import LLMExtractor
from app.core.validator import SchemaValidator
from app.core.config import CONFIG
from app.core.field_settings import FieldSettings
from ..warnings import WarningItem
from ..normalize import normalize_whitespace
from ..summary import (
    build_selection_rationale,
    build_short_summary,
    clamp_summary_text,
)

class ExtractionPipeline:
    def __init__(
        self,
        schema: Dict[str, Any],
        system_prompt_path: str,
        user_tmpl_path: str,
        field_settings: FieldSettings,
        field_guidelines_path: Optional[str] = None,
        summary_system_prompt_path: Optional[str] = None,
        summary_user_tmpl_path: Optional[str] = None,
    ):
        self.field_settings = field_settings
        self.schema = self.field_settings.apply_to_schema(schema)
        self.validator = SchemaValidator(self.schema)
        self.rules = RuleBasedExtractor()
        self.llm = None
        self.summary_llm = None
        self._summary_schema = {
            "type": "object",
            "properties": {
                "КраткоеСодержание": {"type": "string"},
                "ОбоснованиеВыбора": {"type": "string"},
                "ОЭЗ_ОКПД2": {"type": "string"},
                "СрокДоговора": {"type": "string"},
                "Ответственный": {"type": "string"},
                "seza_ТипДоговора": {"type": "string"},
                "СпособОплаты": {"type": "string"},
            },
        }
        if CONFIG.use_llm:
            self.llm = LLMExtractor(
                self.schema,
                system_prompt_path,
                user_tmpl_path,
                field_guidelines_path,
            )
            if summary_system_prompt_path and summary_user_tmpl_path:
                self.summary_llm = LLMExtractor(
                    self._summary_schema,
                    summary_system_prompt_path,
                    summary_user_tmpl_path,
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

        summary_text = ""
        rationale_text = ""
        okpd2_code = ""
        contract_term = ""
        responsible_person = ""
        contract_type = ""
        payment_method = ""
        prompts: List[str] = []
        raw_outputs: List[str] = []

        if self.summary_llm is not None:
            try:
                summary_payload = await self.summary_llm.extract(cleaned_text, {})
            except Exception:
                summary_payload = {}
            candidate_summary = (
                summary_payload.get("КраткоеСодержание")
                if isinstance(summary_payload, dict)
                else ""
            )
            candidate_rationale = (
                summary_payload.get("ОбоснованиеВыбора")
                if isinstance(summary_payload, dict)
                else ""
            )
            candidate_okpd2 = (
                summary_payload.get("ОЭЗ_ОКПД2")
                if isinstance(summary_payload, dict)
                else ""
            )
            candidate_contract_term = (
                summary_payload.get("СрокДоговора")
                if isinstance(summary_payload, dict)
                else ""
            )
            candidate_responsible = (
                summary_payload.get("Ответственный")
                if isinstance(summary_payload, dict)
                else ""
            )
            candidate_contract_type = (
                summary_payload.get("seza_ТипДоговора")
                if isinstance(summary_payload, dict)
                else ""
            )
            candidate_payment_method = (
                summary_payload.get("СпособОплаты")
                if isinstance(summary_payload, dict)
                else ""
            )
            
            if isinstance(candidate_summary, str):
                summary_text = clamp_summary_text(candidate_summary)
            if isinstance(candidate_rationale, str):
                rationale_text = clamp_summary_text(candidate_rationale)
            if isinstance(candidate_okpd2, str):
                okpd2_code = candidate_okpd2.strip()
            if isinstance(candidate_contract_term, str):
                contract_term = candidate_contract_term.strip()
            if isinstance(candidate_responsible, str):
                responsible_person = candidate_responsible.strip()
            if isinstance(candidate_contract_type, str):
                contract_type = candidate_contract_type.strip()
            if isinstance(candidate_payment_method, str):
                payment_method = candidate_payment_method.strip()
                
            if getattr(self.summary_llm, "last_prompt", ""):
                prompts.append(self.summary_llm.last_prompt)
            if getattr(self.summary_llm, "last_raw", ""):
                raw_outputs.append(self.summary_llm.last_raw)

        # 1) Правила
        partial = await self.rules.extract(cleaned_text, {})

        # 2) LLM (если включен)
        prompt = ""
        if self.llm is not None:
            self.field_settings.refresh_prompts()
            aggregated = dict(partial)
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

        if okpd2_code:
            data["ОЭЗ_ОКПД2"] = okpd2_code
        
        if contract_term:
            data["СрокДоговора"] = contract_term
        
        if responsible_person:
            existing_responsible = data.get("Ответственный")
            if not isinstance(existing_responsible, str) or not existing_responsible.strip():
                data["Ответственный"] = responsible_person
        
        if contract_type:
            existing_contract_type = data.get("seza_ТипДоговора")
            if not isinstance(existing_contract_type, str) or not existing_contract_type.strip():
                data["seza_ТипДоговора"] = contract_type
        
        if payment_method:
            existing_payment_method = data.get("СпособОплаты")
            if not isinstance(existing_payment_method, str) or not existing_payment_method.strip():
                data["СпособОплаты"] = payment_method
                
        # 3) Валидация
        filtered_data = self.field_settings.filter_payload(data)
        errors = self.validator.validate(filtered_data)

        if not summary_text:
            summary_text = build_short_summary(filtered_data, cleaned_text)
        if summary_text:
            filtered_data["КраткоеСодержание"] = summary_text

        if not rationale_text:
            rationale_text = build_selection_rationale(filtered_data, cleaned_text)
        if rationale_text:
            filtered_data["ОбоснованиеВыбора"] = rationale_text

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

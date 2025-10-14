import re
from typing import Dict, Any
from .base import BaseExtractor
from ..normalize import normalize_whitespace, extract_number

class RuleBasedExtractor(BaseExtractor):
    SUM_PAT = re.compile(r'(?:итого|сумма\s*договора)\s*[:\-]?\s*([0-9\s\u00A0.,]+)', re.IGNORECASE)
    VAT_PAT = re.compile(r'НДС\s*(?:[:\-]?\s*)?([0-9\s\u00A0.,]+)', re.IGNORECASE)
    VAT_RATE_PAT = re.compile(r'(?:ставка\s*ндс|ндс)\s*[:\-]?\s*(\d{1,2})\s*%?', re.IGNORECASE)

    _ORG_PREFIX = r'(?:[AА][OО]|[OО]{3}|[PР][AА][OО]|[ZЗ][AА][OО])'
    ORG_PAT = re.compile(
        rf'{_ORG_PREFIX}\s*(?:"[^"\n]+"|«[^»\n]+»)',
        re.IGNORECASE,
    )
    DATE_PAT = re.compile(r'(\d{2})[.](\d{2})[.](\d{4})')

    async def extract(
        self, text: str, partial: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any]:
        text_norm = normalize_whitespace(text)

        result = dict(partial)

        # Сумма (итого)
        m = self.SUM_PAT.search(text_norm)
        if m and (val := extract_number(m.group(1))) is not None:
            result.setdefault("Сумма", val)

        # НДС сумма
        m = self.VAT_PAT.search(text_norm)
        if m and (val := extract_number(m.group(1))) is not None:
            result.setdefault("СуммаНДС", val)

        # Ставка НДС
        m = self.VAT_RATE_PAT.search(text_norm)
        if m:
            result.setdefault("СтавкаНДС", m.group(1))

        # Организации (грубая эвристика: первая — "Организация", вторая — "Контрагент")
        orgs = self.ORG_PAT.findall(text_norm)
        if orgs:
            normalized = [item.strip() for item in orgs if item.strip()]
            org_value = result.get("Организация")
            counterparty_value = result.get("Контрагент")
            for value in normalized:
                if not org_value:
                    org_value = value
                    result["Организация"] = value
                    continue
                if not counterparty_value and value != org_value:
                    counterparty_value = value
                    result["Контрагент"] = value
                    break

        # Дата создания (если не было) — текущая
        result.setdefault("ДатаСоздания", __import__("datetime").datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))

        # Валюта по умолчанию
        result.setdefault("Валюта", "RUB")

        return result

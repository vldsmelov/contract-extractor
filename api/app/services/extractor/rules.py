import re
from typing import Dict, Any
from .base import BaseExtractor
from ..normalize import normalize_whitespace, extract_number

class RuleBasedExtractor(BaseExtractor):
    SUM_PAT = re.compile(r'(?:итого|сумма\s*договора)\s*[:\-]?\s*([0-9\s\u00A0.,]+)', re.IGNORECASE)
    VAT_PAT = re.compile(r'НДС\s*(?:[:\-]?\s*)?([0-9\s\u00A0.,]+)', re.IGNORECASE)
    VAT_RATE_PAT = re.compile(r'(?:ставка\s*ндс|ндс)\s*[:\-]?\s*(\d{1,2})\s*%?', re.IGNORECASE)

    ORG_PAT = re.compile(r'(?:(?:АО|ООО|ПАО|ЗАО)\s*\"[^\"]+\"|(?:(?:АО|ООО|ПАО|ЗАО)\s+[\w\s\"«».-]{3,}))')
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
            if "Организация" not in result:
                result["Организация"] = orgs[0].strip()
            if len(orgs) > 1 and "Контрагент" not in result:
                result["Контрагент"] = orgs[1].strip()

        # Дата создания (если не было) — текущая
        result.setdefault("ДатаСоздания", __import__("datetime").datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))

        # Валюта по умолчанию
        result.setdefault("Валюта", "RUB")

        return result

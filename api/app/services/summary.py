"""Utility helpers for building short summaries of extracted contract data."""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

_MAX_SUMMARY_LENGTH = 300

# Keywords mapped to category labels written in the form expected after
# "приобретение" (genitive case for better readability).
_CATEGORY_KEYWORDS: Dict[str, tuple[str, ...]] = {
    "оргтехники": (
        "оргтех", "ноут", "компьютер", "моноблок", "пк", "сервер", "принтер",
        "мфу", "сканер", "копир", "плоттер", "монитор", "проектор", "перфоратор",
    ),
    "бытовой техники": (
        "холодиль", "морозил", "чайник", "микроволн", "пылесос", "посудомой",
        "стиральн", "варочн", "плита", "электроплит", "блендер", "кухонн",
    ),
    "бытовой электроники": (
        "телевиз", "смарт", "планш", "колонк", "акуст", "наушн", "плеер",
        "проектор", "камера", "фотоап", "видеокам", "магнитол",
    ),
    "офисной мебели": (
        "кресл", "стол", "стул", "шкаф", "гардер", "тумб", "диван", "мебел",
    ),
    "строительных материалов": (
        "цемент", "бетон", "кирпич", "арматур", "панел", "гипс", "смесь",
        "строит", "штукатур", "профил", "плитк",
    ),
    "промышленного оборудования": (
        "оборудован", "станок", "насос", "компресс", "агрегат", "конвейер",
        "установк", "машин", "технол", "генератор",
    ),
    "медицинского оборудования": (
        "медиц", "медтех", "рентген", "томограф", "аппарат", "диагност",
        "хирург", "лаборатор", "стерилиз",
    ),
    "транспортных средств": (
        "автомоб", "машин", "самосвал", "трактор", "автобус", "спецтех",
        "транспорт", "экскаватор", "погрузч", "кроссовер",
    ),
    "услуг": (
        "услуг", "работ", "монтаж", "обслужив", "ремонт", "проектир", "аутсорс",
    ),
    "программного обеспечения": (
        "программ", "лиценз", "software", "софт", "платформ",
    ),
}

# Mapping of OKPD2 prefixes to category labels.
_OKPD2_CATEGORY_MAP: Dict[str, str] = {
    "26": "оргтехники",
    "27": "бытовой электроники",
    "28": "промышленного оборудования",
    "29": "транспортных средств",
    "30": "транспортных средств",
    "31": "офисной мебели",
    "32": "медицинского оборудования",
    "33": "услуг",
    "35": "энергии",
    "38": "утилизации",
    "41": "строительных работ",
    "42": "строительных работ",
    "43": "строительных работ",
    "45": "услуг",
    "46": "товаров",
}

_LEGAL_FORMS = (
    "ООО", "АО", "ПАО", "ЗАО", "ОАО", "ИП", "АНО", "ГУП", "МУП", "ФГУП",
    "СПАО", "НКО", "ТСЖ", "ПК", "АОЗТ",
)

_OKPD_PATTERN = re.compile(r"\b(\d{2})\.(\d{2})(?:\.(\d{1,2}))?\b")


def clamp_summary_text(text: str) -> str:
    """Normalize spacing and trim the text to the maximum allowed length."""

    if not isinstance(text, str):
        return ""

    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return ""

    return _trim_summary(normalized, _MAX_SUMMARY_LENGTH)


def build_short_summary(data: Dict[str, Any], source_text: str) -> str:
    """Return a compact textual summary (≤300 characters) of the contract."""

    parties_line = _build_parties_line(data)
    amount_line = _build_amount_line(data)
    subject_line = _build_subject_line(data, source_text)

    parts = [part for part in (parties_line, amount_line, subject_line) if part]
    if not parts:
        return ""

    summary = " ".join(parts).strip()
    return _trim_summary(summary, _MAX_SUMMARY_LENGTH)


def build_selection_rationale(data: Dict[str, Any], source_text: str) -> str:
    """Heuristically justify the supplier choice within the 300-character limit."""

    supplier = _normalize_party_name(data.get("Контрагент"))
    intro = f"Выбор {supplier} обоснован:" if supplier else "Выбор поставщика обоснован:"

    reasons: List[str] = []

    total = _to_float(data.get("Сумма"))
    if total is not None:
        reasons.append(f"цена {_format_money(total)} руб.")

    vat_fragment = _build_vat_reason(data)
    if vat_fragment:
        reasons.append(vat_fragment)

    payment_fragment = _build_payment_fragment(data.get("СпособОплаты"))
    if payment_fragment:
        reasons.append(payment_fragment)

    categories = _detect_categories(data, source_text)
    if categories:
        reasons.append(f"предмет — {_join_categories(categories)}")

    if not reasons:
        return _trim_summary(f"{intro.rstrip(':')}.", _MAX_SUMMARY_LENGTH)

    body = "; ".join(reasons)
    rationale = f"{intro} {body}."
    return _trim_summary(rationale, _MAX_SUMMARY_LENGTH)


def _build_parties_line(data: Dict[str, Any]) -> str:
    buyer = _normalize_party_name(data.get("Организация"))
    seller = _normalize_party_name(data.get("Контрагент"))

    if buyer and seller:
        return f"Договор: {buyer} ⇄ {seller}."
    if buyer:
        return f"Договор: {buyer}."
    if seller:
        return f"Договор: {seller}."
    return ""


def _build_amount_line(data: Dict[str, Any]) -> str:
    total = _to_float(data.get("Сумма"))
    vat_amount = _to_float(data.get("СуммаНДС"))
    vat_rate = _to_float(data.get("СтавкаНДС"))

    components: List[str] = []
    if total is not None:
        components.append(f"Сумма: {_format_money(total)} руб.")
    elif vat_amount is not None:
        components.append(f"Сумма: {_format_money(vat_amount)} руб.")

    vat_fragment = _build_vat_fragment(vat_amount, vat_rate)
    if vat_fragment:
        if components:
            components[-1] = f"{components[-1]} {vat_fragment}"
        else:
            components.append(f"{vat_fragment.capitalize()}")

    return " ".join(components)


def _build_vat_fragment(vat_amount: Optional[float], vat_rate: Optional[float]) -> str:
    if vat_rate is not None:
        if vat_rate <= 0:
            return "(без НДС)"
        rate_str = _format_rate(vat_rate)
        if vat_amount is not None:
            return f"(в т.ч. НДС {rate_str}% — {_format_money(vat_amount)} руб.)"
        return f"(в т.ч. НДС {rate_str}%)"
    if vat_amount is not None:
        return f"(в т.ч. НДС — {_format_money(vat_amount)} руб.)"
    return ""


def _build_subject_line(data: Dict[str, Any], source_text: str) -> str:
    categories = _detect_categories(data, source_text)
    if categories:
        joined = _join_categories(categories)
        return f"Предмет: приобретение {joined}."
    return "Предмет: закупка товаров."


def _build_vat_reason(data: Dict[str, Any]) -> str:
    vat_rate = _to_float(data.get("СтавкаНДС"))
    vat_amount = _to_float(data.get("СуммаНДС"))

    if vat_rate is not None:
        if vat_rate <= 0:
            return "без НДС"
        fragment = f"НДС {_format_rate(vat_rate)}%"
        if vat_amount is not None:
            fragment += " выделен"
        return fragment

    if vat_amount is not None:
        return "НДС выделен"

    return ""


def _build_payment_fragment(value: Any) -> str:
    if not value:
        return ""
    if not isinstance(value, str):
        value = str(value)

    cleaned = re.sub(r"\s+", " ", value).strip()
    if not cleaned:
        return ""

    return f"оплата — {cleaned}"


def _detect_categories(data: Dict[str, Any], source_text: str) -> List[str]:
    categories: List[str] = []
    text_parts: List[str] = []

    for key in ("Содержание", "ОЭЗ_Предмет"):
        value = data.get(key)
        if isinstance(value, str):
            text_parts.append(value)

    if source_text:
        text_parts.append(source_text)

    combined_text = " \n ".join(text_parts).lower()

    for label, keywords in _CATEGORY_KEYWORDS.items():
        if any(keyword.lower() in combined_text for keyword in keywords):
            _append_unique(categories, label)

    for match in _OKPD_PATTERN.finditer(combined_text):
        prefix = match.group(1)
        mapped = _OKPD2_CATEGORY_MAP.get(prefix)
        if mapped:
            _append_unique(categories, mapped)

    return categories


def _append_unique(items: List[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _join_categories(categories: Iterable[str]) -> str:
    items = list(categories)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} и {items[1]}"
    return ", ".join(items[:-1]) + f" и {items[-1]}"


def _normalize_party_name(value: Any) -> Optional[str]:
    if not value:
        return None
    if not isinstance(value, str):
        value = str(value)

    name = re.sub(r"\s*\([^)]*\)", "", value)
    name = re.sub(r"\s+", " ", name).strip().strip(',;')
    if not name:
        return None

    match = re.match(rf"^(?P<body>.+?)\s+(?P<form>{'|'.join(_LEGAL_FORMS)})$", name, re.IGNORECASE)
    if match:
        body = match.group("body").strip(' «»"')
        form = match.group("form").upper()
        if body:
            name = f"{form} «{_clean_quotes(body)}»"
        else:
            name = form
    else:
        form_match = re.match(rf"^(?P<form>{'|'.join(_LEGAL_FORMS)})\s+(?P<body>.+)$", name, re.IGNORECASE)
        if form_match:
            form = form_match.group("form").upper()
            body = form_match.group("body").strip(' «»"')
            if body:
                name = f"{form} «{_clean_quotes(body)}»"
            else:
                name = form
        else:
            name = _replace_quotes(name)

    return name


def _clean_quotes(text: str) -> str:
    cleaned = text.replace('«', '').replace('»', '').replace('"', '')
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _replace_quotes(text: str) -> str:
    result: List[str] = []
    open_quote = True
    for ch in text:
        if ch == '"':
            result.append('«' if open_quote else '»')
            open_quote = not open_quote
        else:
            result.append(ch)
    return "".join(result)


def _format_money(value: float) -> str:
    rounded = round(value + 1e-8, 2)
    if abs(rounded - round(rounded)) < 0.005:
        return _format_int(int(round(rounded)))
    return f"{rounded:,.2f}".replace(",", " ").replace(".", ",")


def _format_int(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def _format_rate(value: float) -> str:
    rounded = round(value, 2)
    if abs(rounded - round(rounded)) < 0.005:
        return str(int(round(rounded)))
    return f"{rounded:.2f}".rstrip('0').rstrip('.')


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.replace("\u00A0", " ").replace(" ", "")
        normalized = normalized.replace(",", ".")
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _trim_summary(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    cutoff = text.rfind(" ", 0, max_len)
    if cutoff == -1 or cutoff < max_len // 2:
        cutoff = max_len
    trimmed = text[:cutoff].rstrip(",.;: ")
    if len(trimmed) < len(text):
        return f"{trimmed}…"
    return trimmed

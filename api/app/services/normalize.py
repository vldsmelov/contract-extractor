import re
from typing import Optional

NBSP = '\u00A0'

_SPECIAL_CHARS_RE = re.compile(r"[^\w\s\.,:;!?()/%«»\"'№\-–—]", re.UNICODE)


def _strip_special_symbols(text: str) -> str:
    """Remove characters that add noise to the document text."""
    return _SPECIAL_CHARS_RE.sub(' ', text)


def normalize_whitespace(text: str) -> str:
    """Collapse whitespace and strip noisy symbols to keep text readable."""
    if not text:
        return ''

    text = text.replace(NBSP, ' ')
    text = _strip_special_symbols(text)
    text = re.sub(r'[\t\r\n]+', ' ', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()

def extract_number(value: str) -> Optional[float]:
    if value is None:
        return None
    # replace NBSP, thin spaces
    value = value.replace('\u00A0', '').replace('\u2009', '')
    # keep digits, dots and commas
    m = re.findall(r'[0-9]+(?:[\s\u00A0]?[0-9]{3})*(?:[\.,][0-9]+)?', value)
    if not m:
        return None
    raw = m[0].replace(' ', '').replace('\u00A0', '')
    raw = raw.replace(',', '.')  # decimal comma -> dot
    try:
        return float(raw)
    except ValueError:
        return None

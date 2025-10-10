from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class WarningItem:
    code: str
    message: str

def to_payload(items: List[WarningItem]) -> List[Dict[str, Any]]:
    return [dict(code=i.code, message=i.message) for i in items]

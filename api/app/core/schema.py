import json
from pathlib import Path
from typing import Dict, Any

def load_schema(schema_path: str) -> Dict[str, Any]:
    p = Path(schema_path)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

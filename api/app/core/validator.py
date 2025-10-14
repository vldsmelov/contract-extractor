import json
import re
from jsonschema import Draft202012Validator, ValidationError
from typing import Any, Dict

class SchemaValidator:
    def __init__(self, schema: Dict[str, Any]):
        self.schema = schema
        self.validator = Draft202012Validator(schema)

    def validate(self, data: Dict[str, Any]):
        errors = sorted(self.validator.iter_errors(data), key=lambda e: e.path)
        return [
            {
                "path": list(e.path),
                "title": self._extract_title(e),
                "message": e.message,
                "validator": e.validator,
            }
            for e in errors
        ]

    def _extract_title(self, error: ValidationError) -> str:
        if error.path:
            return ".".join(str(part) for part in error.path)
        if error.validator == "required":
            message = error.message or ""
            match = re.search(r"'([^']+)' is a required property", message)
            if match:
                return match.group(1)
            # fall back to the first required field mentioned
            if isinstance(error.validator_value, list) and error.validator_value:
                return str(error.validator_value[0])
        if error.schema_path:
            return ".".join(str(part) for part in error.schema_path)
        return ""

    def get_schema(self) -> Dict[str, Any]:
        return self.schema
